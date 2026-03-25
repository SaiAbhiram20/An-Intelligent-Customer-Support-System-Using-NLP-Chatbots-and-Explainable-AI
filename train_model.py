import os
import psycopg2
from dotenv import load_dotenv
from datasets import Dataset
from transformers import AutoTokenizer, AutoModelForSequenceClassification, Trainer, TrainingArguments
import torch

load_dotenv()

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_NAME = os.environ.get("DB_NAME", "postgres")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASS = os.environ.get("DB_PASSWORD", "password")

MODEL_NAME = "valhalla/distilbart-mnli-12-1" 
OUTPUT_DIR = "./models/custom-intent/"

INTENT_MAP = {
    "order_status": 0, "refund": 1, "shipping": 2, "technical": 3, 
    "subscription": 4, "account": 5, "billing": 6, "greeting": 7, "unknown": 8
}

def fetch_training_data():
    conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, database=DB_NAME, user=DB_USER, password=DB_PASS)
    cur = conn.cursor()
    # Fetch interactions flagged for retraining or where rating was low
    cur.execute("""
        SELECT i.user_message, i.detected_intent, f.rating 
        FROM chat_interactions i
        LEFT JOIN feedback f ON i.id = f.interaction_id
        WHERE f.retrain_flag = TRUE OR f.rating <= 3
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    texts = []
    labels = []
    
    for row in rows:
        msg, intent, rating = row
        if not msg or intent not in INTENT_MAP:
            continue
        
        # In a real scenario, an admin would label the correct intent. 
        # Here we just train on the detected intent assuming we want to reinforce it, 
        # or we could parse the admin's manual correction if we had a column for it.
        # For demonstration of the pipeline, we map it to our integer classes.
        texts.append(msg)
        labels.append(INTENT_MAP[intent])
        
    return texts, labels

def train():
    texts, labels = fetch_training_data()
    
    if len(texts) < 5:
        print(f"Not enough training data yet! ({len(texts)} samples). Need at least 5.")
        return

    print(f"Loaded {len(texts)} samples for training.")
    
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME, 
        num_labels=len(INTENT_MAP), 
        ignore_mismatched_sizes=True
    )
    
    # Create HF Dataset
    encodings = tokenizer(texts, truncation=True, padding=True, max_length=128)
    dataset = Dataset.from_dict({
        'input_ids': encodings['input_ids'],
        'attention_mask': encodings['attention_mask'],
        'labels': labels
    })
    
    training_args = TrainingArguments(
        output_dir=OUTPUT_DIR,
        num_train_epochs=3,
        per_device_train_batch_size=8,
        logging_dir='./logs',
        logging_steps=10,
        save_strategy="epoch"
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
    )

    print("Beginning fine-tuning...")
    trainer.train()
    
    print(f"Training complete! Saving model to {OUTPUT_DIR}")
    trainer.save_model(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)

if __name__ == "__main__":
    train()
