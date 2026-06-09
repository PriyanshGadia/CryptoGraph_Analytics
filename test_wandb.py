import os
from pathlib import Path
from dotenv import load_dotenv
import wandb

def main():
    load_dotenv(Path("ml/.env"))
    key = os.environ.get("WANDB_API_KEY")
    if key:
        print("WANDB_API_KEY found in ml/.env, attempting login...")
        try:
            wandb.login(key=key)
            print("W&B Login Successful! ✅")
        except Exception as e:
            print(f"W&B Login Failed ❌: {e}")
    else:
        print("WANDB_API_KEY not found in ml/.env ❌")

if __name__ == "__main__":
    main()
