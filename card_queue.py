from typing import Dict, Any, Optional, List, Deque
from collections import deque
from fastapi import BackgroundTasks
import asyncio
from datetime import datetime
import logging
import json
from enum import Enum, auto
from generator.card_generator import generate_card, generate_card_image
from tenacity import retry, stop_after_attempt, wait_exponential, RetryError
from db_ops.card_ops import create_card

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class TaskState(str, Enum):
    """Explicit states for task processing."""
    QUEUED = "queued"         # Task is in queue
    GENERATING = "generating" # Generating card data
    CREATING_IMAGE = "creating_image" # Creating card image
    SAVING = "saving"         # Saving to Firestore
    COMPLETED = "completed"   # Task completed successfully
    FAILED = "failed"         # Task failed
    NOT_FOUND = "not_found"   # Task doesn't exist

class CardGenerationError(Exception):
    """Base exception for card generation errors."""
    def __init__(self, message: str, state: TaskState):
        self.message = message
        self.state = state
        super().__init__(message)

class QueueFullError(CardGenerationError):
    """Raised when the queue is at capacity."""
    def __init__(self):
        super().__init__("Queue is at capacity", TaskState.FAILED)

class TaskNotFoundError(CardGenerationError):
    """Raised when a task is not found."""
    def __init__(self, task_id: str):
        super().__init__(f"Task {task_id} not found", TaskState.NOT_FOUND)

class Task:
    """Represents a card generation task."""
    def __init__(self, task_id: str, user_id: str, rarity: Optional[str] = None):
        self.task_id = task_id
        self.user_id = user_id
        self.rarity = rarity
        self.state = TaskState.QUEUED
        self.created_at = datetime.utcnow()
        self.updated_at = self.created_at
        self.completed_at: Optional[datetime] = None
        self.card_id: Optional[str] = None
        self.error: Optional[str] = None
        self.retry_count = 0

    def update_state(self, new_state: TaskState, error: Optional[str] = None) -> None:
        """Update task state with logging."""
        old_state = self.state
        self.state = new_state
        self.updated_at = datetime.utcnow()
        if error:
            self.error = error
        if new_state == TaskState.COMPLETED:
            self.completed_at = self.updated_at
        logger.info(f"Task {self.task_id} state changed: {old_state} -> {new_state}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary."""
        return {
            'task_id': self.task_id,
            'user_id': self.user_id,
            'state': self.state,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'completed_at': self.completed_at,
            'card_id': self.card_id,
            'error': self.error,
            'retry_count': self.retry_count
        }

class CardGenerationQueue:
    def __init__(self, max_queue_size: int = 100, max_concurrent_tasks: int = 3):
        self.queue: Deque[Task] = deque(maxlen=max_queue_size)
        self.processing: Dict[str, Task] = {}
        self.completed: Dict[str, Task] = {}
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(max_concurrent_tasks)
        self._stop_event = asyncio.Event()
        
    async def add_to_queue(self, task_id: str, user_id: str, rarity: Optional[str] = None) -> str:
        """Add a card generation task to the queue."""
        try:
            if len(self.queue) >= self.queue.maxlen:
                raise QueueFullError()
                
            async with self._lock:
                task = Task(task_id, user_id, rarity)
                self.queue.append(task)
                logger.info(f"Added task {task_id} to queue. Queue size: {len(self.queue)}")
                return task_id
        except QueueFullError:
            raise
        except Exception as e:
            logger.error(f"Error adding task to queue: {e}")
            raise CardGenerationError(str(e), TaskState.FAILED)
            
    async def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Get the status of a specific task."""
        try:
            # Check processing tasks
            if task_id in self.processing:
                return self.processing[task_id].to_dict()
                
            # Check completed tasks
            if task_id in self.completed:
                return self.completed[task_id].to_dict()
                
            # Check queue
            for task in self.queue:
                if task.task_id == task_id:
                    return task.to_dict()
                    
            raise TaskNotFoundError(task_id)
            
        except TaskNotFoundError as e:
            return {'state': e.state, 'task_id': task_id}
        except Exception as e:
            logger.error(f"Error getting task status: {e}")
            return {
                'state': TaskState.FAILED,
                'task_id': task_id,
                'error': 'Failed to get task status'
            }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True
    )
    async def _generate_card(self, task: Task) -> Dict[str, Any]:
        """Generate a card with retries."""
        try:
            task.update_state(TaskState.GENERATING)
            
            # Generate card data
            card_data = generate_card(task.rarity)
            card_data['user_id'] = task.user_id
            
            task.update_state(TaskState.CREATING_IMAGE)
            
            
            # Generate and upload image
            image_url, b2_url = generate_card_image(card_data)
            filename = f"card_{card_data['set_name']}_{card_data['card_number']}.png"
            task.update_state(TaskState.SAVING)
            
            
            # Create card in Firestore
            card = create_card(card_data, image_url, filename)
            return card
            
        except Exception as e:
            logger.error(f"Error generating card: {e}")
            raise
    async def process_next(self) -> Optional[Dict[str, Any]]:
        """Process the next card in the queue."""
        async with self._lock:
            if not self.queue:
                return None
                
            task = self.queue.popleft()
            self.processing[task.task_id] = task
            
        try:
            async with self._semaphore:
                try:
                    card = await self._generate_card(task)
                    task.card_id = card['id']
                    task.update_state(TaskState.COMPLETED)
                    
                except RetryError as e:
                    task.update_state(TaskState.FAILED, "Maximum retries exceeded")
                    
                except Exception as e:
                    task.update_state(TaskState.FAILED, str(e))
                
                # Move to completed
                self.completed[task.task_id] = task
                return task.to_dict()
                
        finally:
            # Always clean up processing state
            if task.task_id in self.processing:
                del self.processing[task.task_id]
            
    async def process_queue(self) -> None:
        """Continuously process the queue."""
        while not self._stop_event.is_set():
            try:
                if self.queue:
                    await self.process_next()
                await asyncio.sleep(1)  # Prevent CPU overuse
            except Exception as e:
                logger.error(f"Error in queue processing: {e}")
                await asyncio.sleep(5)  # Back off on error
            
    def clean_old_results(self, max_age_hours: int = 24) -> None:
        """Clean up old results."""
        try:
            current_time = datetime.utcnow()
            to_remove = []
            
            for task_id, task in self.completed.items():
                if task.completed_at and (current_time - task.completed_at).total_seconds() > max_age_hours * 3600:
                    to_remove.append(task_id)
                    
            for task_id in to_remove:
                del self.completed[task_id]
                
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