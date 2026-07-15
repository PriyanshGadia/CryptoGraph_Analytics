import os
import sys
import json

# Adjust path to import backend modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'backend')))

from app.db.database import SessionLocal
from app.db.models import Prediction

def main():
    db = SessionLocal()
    try:
        p = db.query(Prediction).filter(Prediction.t_shap_attributions.isnot(None)).first()
        if p:
            print("Found prediction with t_shap_attributions:")
            print(f"t_shap_attributions type: {type(p.t_shap_attributions)}")
            if isinstance(p.t_shap_attributions, str):
                t_shap = json.loads(p.t_shap_attributions)
            else:
                t_shap = p.t_shap_attributions
            print(f"Keys: {list(t_shap.keys())}")
            print(f"Values: {t_shap}")
        else:
            print("No prediction with t_shap_attributions found.")
            
        p2 = db.query(Prediction).filter(Prediction.shap_values.isnot(None)).first()
        if p2:
            print("Found prediction with shap_values:")
            print(f"shap_values type: {type(p2.shap_values)}")
            print(f"shap_values: {p2.shap_values}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == '__main__':
    main()
