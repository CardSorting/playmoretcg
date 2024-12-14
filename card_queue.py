from typing import Dict, Any, Optional, List, Deque
from collections import deque
from fastapi import BackgroundTasks
import asyncio
from datetime import datetime
import logging
import json
from card_generator import generate_card, generate_card_image
import firestore_db
from tenacity import retry, stop_after_attempt, wait_exponential, RetryError

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class CardGenerationError(Exception):
    """Base exception for card generation errors."""
    pass

class QueueFullError(CardGenerationError):
    """Raised when the queue is at capacity."""
    pass

class TaskNotFoundError(CardGenerationError):
    """Raised when a task is not found."""
    pass

def serialize_datetime(dt: datetime) -> Optional[str]:
    """Convert datetime to ISO format string."""
    try:
        return dt.isoformat() if dt else None
    except Exception as e:
        logger.error(f"Error serializing datetime: {e}")
        return None

def serialize_task(task: Dict[str, Any]) -> Dict[str, Any]:
    """Convert task data to JSON-serializable format with error handling."""
    try:
        serialized = task.copy()
        if 'created_at' in serialized:
            serialized['created_at'] = serialize_datetime(serialized['created_at'])
        if 'completed_at' in serialized:
            serialized['completed_at'] = serialize_datetime(serialized['completed_at'])
            
        # Ensure all values are JSON serializable
        json.dumps(serialized)
        return serialized
    except Exception as e:
        logger.error(f"Error serializing task: {e}")
        # Return a safe fallback
        return {
            'status': 'error',
            'task_id': task.get('task_id', 'unknown'),
            'error': 'Task serialization failed'
        }

class CardGenerationQueue:
    def __init__(self, max_queue_size: int = 100, max_concurrent_tasks: int = 3):
        self.queue: Deque[Dict[str, Any]] = deque(maxlen=max_queue_size)
        self.processing: Dict[str, Dict[str, Any]] = {}
        self.results: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(max_concurrent_tasks)
        self._stop_event = asyncio.Event()
        
    async def add_to_queue(self, task_id: str, user_id: str, rarity: Optional[str] = None) -> str:
        """Add a card generation task to the queue with error handling."""
        try:
            if len(self.queue) >= self.queue.maxlen:
                raise QueueFullError("Queue is at capacity")
                
            async with self._lock:
                task = {
                    'task_id': task_id,
                    'user_id': user_id,
                    'rarity': rarity,
                    'status': 'queued',
                    'created_at': datetime.utcnow(),
                    'retry_count': 0
                }
                self.queue.append(task)
                logger.info(f"Added task {task_id} to queue")
                return task_id
        except QueueFullError:
            raise
        except Exception as e:
            logger.error(f"Error adding task to queue: {e}")
            raise CardGenerationError(f"Failed to add task: {str(e)}")
            
    async def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Get the status of a specific task with error handling."""
        try:
            # Check processing tasks
            if task_id in self.processing:
                return serialize_task({
                    'status': 'processing',
                    'task_id': task_id,
                    'created_at': self.processing[task_id]['created_at']
                })
                
            # Check completed results
            if task_id in self.results:
                return serialize_task(self.results[task_id])
                
            # Check queue
            for task in self.queue:
                if task['task_id'] == task_id:
                    return serialize_task({
                        'status': 'queued',
                        'task_id': task_id,
                        'created_at': task['created_at']
                    })
                    
            raise TaskNotFoundError(f"Task {task_id} not found")
            
        except TaskNotFoundError:
            return {'status': 'not_found', 'task_id': task_id}
        except Exception as e:
            logger.error(f"Error getting task status: {e}")
            return {
                'status': 'error',
                'task_id': task_id,
                'error': 'Failed to get task status'
            }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True
    )
    async def _generate_card(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a card with retries and error handling."""
        try:
            # Generate card data
            card_data = generate_card(task['rarity'])
            card_data['user_id'] = task['user_id']
            
            # Generate and upload image
            image_url, b2_url = generate_card_image(card_data)
            filename = f"card_{card_data['set_name']}_{card_data['card_number']}.png"
            
            # Create card in Firestore
            return firestore_db.create_card(card_data, b2_url, filename)
        except Exception as e:
            logger.error(f"Error generating card: {e}")
            raise
        
    async def process_next(self) -> Optional[Dict[str, Any]]:
        """Process the next card in the queue with error handling."""
        async with self._lock:
            if not self.queue:
                return None
                
            task = self.queue.popleft()
            self.processing[task['task_id']] = task
            
        try:
            async with self._semaphore:
                try:
                    card = await self._generate_card(task)
                    
                    # Store success result
                    result = {
                        'status': 'completed',
                        'task_id': task['task_id'],
                        'card_id': card['id'],
                        'created_at': task['created_at'],
                        'completed_at': datetime.utcnow()
                    }
                    
                except RetryError as e:
                    # All retries failed
                    result = {
                        'status': 'error',
                        'task_id': task['task_id'],
                        'error': 'Maximum retries exceeded',
                        'created_at': task['created_at'],
                        'completed_at': datetime.utcnow()
                    }
                    
                except Exception as e:
                    # Unexpected error
                    result = {
                        'status': 'error',
                        'task_id': task['task_id'],
                        'error': str(e),
                        'created_at': task['created_at'],
                        'completed_at': datetime.utcnow()
                    }
                
                self.results[task['task_id']] = result
                return serialize_task(result)
                
        finally:
            # Always clean up processing state
            if task['task_id'] in self.processing:
                del self.processing[task['task_id']]
            
    async def process_queue(self) -> None:
        """Continuously process the queue with error handling."""
        while not self._stop_event.is_set():
            try:
                if self.queue:
                    await self.process_next()
                await asyncio.sleep(1)  # Prevent CPU overuse
            except Exception as e:
                logger.error(f"Error in queue processing: {e}")
                await asyncio.sleep(5)  # Back off on error
            
    def clean_old_results(self, max_age_hours: int = 24) -> None:
        """Clean up old results with error handling."""
        try:
            current_time = datetime.utcnow()
            to_remove = []
            
            for task_id, result in self.results.items():
                try:
                    completed_at = result.get('completed_at')
                    if completed_at and (current_time - completed_at).total_seconds() > max_age_hours * 3600:
                        to_remove.append(task_id)
                except Exception as e:
                    logger.error(f"Error processing result {task_id}: {e}")
                    
            for task_id in to_remove:
                try:
                    del self.results[task_id]
                except Exception as e:
                    logger.error(f"Error removing result {task_id}: {e}")
                    
        except Exception as e:
            logger.error(f"Error cleaning old results: {e}")

    async def shutdown(self) -> None:
        """Gracefully shut down the queue."""
        self._stop_event.set()
        # Wait for current processing to complete
        if self.processing:
            await asyncio.sleep(5)

# Create global queue instance
card_queue = CardGenerationQueue()

# Background task to process queue
async def run_queue_processor() -> None:
    try:
        await card_queue.process_queue()
    except Exception as e:
        logger.error(f"Queue processor error: {e}")
        # Attempt to restart the processor
        await asyncio.sleep(5)
        await run_queue_processor()

# Function to start queue processor
def start_queue_processor(background_tasks: BackgroundTasks) -> None:
    background_tasks.add_task(run_queue_processor)

# Function to clean old results periodically
async def clean_old_results() -> None:
    while True:
        try:
            await asyncio.sleep(3600)  # Clean every hour
            card_queue.clean_old_results()
        except Exception as e:
            logger.error(f"Error in cleanup task: {e}")
            await asyncio.sleep(300)  # Back off on error