
import joblib
import numpy as np
import pandas as pd
from datetime import datetime
from sentence_transformers import SentenceTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
import torch.nn.functional as F
import torch
import torch.nn as nn
import torch.optim as optim

# 1. Load required objects
xgb_model = joblib.load("xgb_category_model.pkl")
svm_model = joblib.load("svm_model.pkl")

#encoder_web = joblib.load("onehot_encoder_web.pkl")         # previously fitted OneHotEncoder on 'Web'
#scaler = joblib.load("scaler.pkl")                         # StandardScaler used on final features
label_encoder = joblib.load("label_encoder_category.pkl")   # LabelEncoder for category labels

input_size = 416
num_classes = 8

class ANNCategoryClassifier(nn.Module):
    def __init__(self, input_size, num_classes):
        super(ANNCategoryClassifier, self).__init__()

        self.fc1 = nn.Linear(input_size, 512)
        self.bn1 = nn.BatchNorm1d(512)
        self.dropout1 = nn.Dropout(0.2)

        self.fc2 = nn.Linear(512, 256)
        self.bn2 = nn.BatchNorm1d(256)
        self.dropout2 = nn.Dropout(0.2)

        self.fc3 = nn.Linear(256, 128)
        self.bn3 = nn.BatchNorm1d(128)
        #self.dropout3 = nn.Dropout(0.3)

        self.fc4 = nn.Linear(128, 64)
        self.bn4 = nn.BatchNorm1d(64)
        #self.dropout4 = nn.Dropout(0.3)

        self.out = nn.Linear(64, num_classes)

    def forward(self, x):
        x = F.relu(self.bn1(self.fc1(x)))
        x = self.dropout1(x)

        x = F.relu(self.bn2(self.fc2(x)))
        x = self.dropout2(x)

        x = F.relu(self.bn3(self.fc3(x)))
       # x = self.dropout3(x)

        x = F.relu(self.bn4(self.fc4(x)))
        #x = self.dropout4(x)

        return self.out(x)  # Raw logits (used with CrossEntropyLoss)

# Load the model
ann_model = ANNCategoryClassifier(input_size, num_classes)
ann_model.load_state_dict(torch.load("ann_categorgy.pth", map_location=torch.device('cpu')))
ann_model.eval()

def extract_date_features(month_year_str):
    try:
        # Parse date in format like "Oct-20"
        date = pd.to_datetime(month_year_str, format='%b-%y')
        return pd.Series({
            'year': date.year,
            'month': date.month,
            'quarter': date.quarter
        })
    except:
        # Fallback in case of parsing error
        print("Except")
        return pd.Series({'year': 0, 'month': 0, 'quarter': 0})


def preprocess_input(statement, web, date_str):
    # STEP 1: BERT Embeddings
    model = SentenceTransformer('paraphrase-MiniLM-L6-v2')
    bert_embeddings = model.encode([statement])
    #print(bert_embeddings)

    # STEP 2.5: Apply Date Feature Extraction
    date_features = extract_date_features(date_str)

    # STEP 3: Source (Web) Encoding
    web_encoder = joblib.load("web_encoder_fake.pkl")  # adjust the path
    web_encoded = web_encoder.transform([[web]])  # double brackets to create 2D shape

    # Step 1: Replace NaNs in date features
    date_features_filled = date_features.fillna(0)
    date_features_array = date_features_filled.values.reshape(1, -1)

    # Step 3: Concatenate again
    final_features = np.hstack([
        bert_embeddings,
        web_encoded,
        date_features_array
    ])

    # Step 4: Replace any remaining NaNs (if any) as safety net
    final_features = np.nan_to_num(final_features, nan=0.0)
    #print(final_features)

    # Step 5: Normalize
    scaler = joblib.load("scaler_fake.pkl")

    # Use transform instead of fit_transform
    final_features_scaled = scaler.transform(final_features)

    return final_features_scaled

def ensemble_predict(statement, web, date):
    # Get preprocessed feature vector
    input_vec = preprocess_input(statement, web, date)

    # Predict probabilities
    prob_ann = predict_ann_proba(input_vec)
    prob_xgb = xgb_model.predict_proba(input_vec)
    prob_svm = svm_model.predict_proba(input_vec)

    # Soft Voting
    avg_prob = (prob_ann + prob_xgb + prob_svm) / 3

    # Final Prediction
    pred_index = np.argmax(avg_prob)
    pred_label = label_encoder.inverse_transform([pred_index])[0]
    confidence = avg_prob[0][pred_index]

    return pred_label, confidence

def predict_ann_proba(input_vec):
    with torch.no_grad():
        input_tensor = torch.tensor(input_vec, dtype=torch.float32)
        logits = ann_model(input_tensor)
        probs = F.softmax(logits, dim=1).numpy()
    return probs

stmt = "YESS!!"
web = "NDTV"
date = "Jan-21"
label, conf = ensemble_predict(stmt, web, date)
print(f"Prediction: {label} (Confidence: {conf:.4f})")

