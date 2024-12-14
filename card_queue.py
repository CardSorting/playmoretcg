from typing import Dict, Any, Optional, List
from collections import deque
from fastapi import BackgroundTasks
import asyncio
from datetime import datetime
import logging
from card_generator import generate_card, generate_card_image
import firestore_db

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class CardGenerationQueue:
    def __init__(self):
        self.queue = deque()
        self.processing = {}  # Track cards being processed
        self.results = {}     # Store results
        self._lock = asyncio.Lock()
        
    async def add_to_queue(self, task_id: str, user_id: str, rarity: Optional[str] = None) -> str:
        """Add a card generation task to the queue."""
        async with self._lock:
            self.queue.append({
                'task_id': task_id,
                'user_id': user_id,
                'rarity': rarity,
                'status': 'queued',
                'created_at': datetime.utcnow(),
            })
            logger.info(f"Added task {task_id} to queue")
            return task_id
            
    async def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Get the status of a specific task."""
        # Check processing tasks
        if task_id in self.processing:
            return {
                'status': 'processing',
                'task_id': task_id,
                'created_at': self.processing[task_id]['created_at']
            }
            
        # Check completed results
        if task_id in self.results:
            return self.results[task_id]
            
        # Check queue
        for task in self.queue:
            if task['task_id'] == task_id:
                return {
                    'status': 'queued',
                    'task_id': task_id,
                    'created_at': task['created_at']
                }
                
        return {'status': 'not_found', 'task_id': task_id}
        
    async def process_next(self) -> Optional[Dict[str, Any]]:
        """Process the next card in the queue."""
        async with self._lock:
            if not self.queue:
                return None
                
            task = self.queue.popleft()
            self.processing[task['task_id']] = task
            
        try:
            # Generate card data
            card_data = generate_card(task['rarity'])
            card_data['user_id'] = task['user_id']
            
            # Generate and upload image
            image_url, b2_url = generate_card_image(card_data)
            filename = f"card_{card_data['set_name']}_{card_data['card_number']}.png"
            
            # Create card in Firestore
            card = firestore_db.create_card(card_data, b2_url, filename)
            
            # Store result
            result = {
                'status': 'completed',
                'task_id': task['task_id'],
                'card_id': card['id'],
                'created_at': task['created_at'],
                'completed_at': datetime.utcnow()
            }
            self.results[task['task_id']] = result
            
            # Clean up processing
            del self.processing[task['task_id']]
            
            logger.info(f"Completed task {task['task_id']}")
            return result
            
        except Exception as e:
            logger.error(f"Error processing task {task['task_id']}: {str(e)}")
            # Store error result
            result = {
                'status': 'error',
                'task_id': task['task_id'],
                'error': str(e),
                'created_at': task['created_at'],
                'completed_at': datetime.utcnow()
            }
            self.results[task['task_id']] = result
            
            # Clean up processing
            del self.processing[task['task_id']]
            return result
            
    async def process_queue(self):
        """Continuously process the queue."""
        while True:
            if self.queue:
                await self.process_next()
            await asyncio.sleep(1)  # Prevent CPU overuse
            
    def clean_old_results(self, max_age_hours: int = 24):
        """Clean up old results to prevent memory bloat."""
        current_time = datetime.utcnow()
        to_remove = []
        
        for task_id, result in self.results.items():
            completed_at = result.get('completed_at')
            if completed_at and (current_time - completed_at).total_seconds() > max_age_hours * 3600:
                to_remove.append(task_id)
                
        for task_id in to_remove:
            del self.results[task_id]

# Create global queue instance
card_queue = CardGenerationQueue()

# Background task to process queue
async def run_queue_processor():
    await card_queue.process_queue()

# Function to start queue processor
def start_queue_processor(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_queue_processor)

# Function to clean old results periodically
async def clean_old_results():
    while True:
        await asyncio.sleep(3600)  # Clean every hour
        card_queue.clean_old_results()