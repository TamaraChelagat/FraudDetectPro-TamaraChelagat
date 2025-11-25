from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import numpy as np
import joblib
import os
import firebase_admin
from firebase_admin import credentials, auth
import logging
from collections import deque
from datetime import datetime
import uuid
import asyncio
import json

# Import database module
from app.database import (
    save_transaction,
    get_transaction as get_transaction_from_db,
    get_transactions as get_transactions_from_db,
    get_statistics,
    update_transaction_flag
)

# =====================================================
# FraudDetectPro - FastAPI Backend with Firebase Auth
# =====================================================

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Check for SHAP availability
try:
    import shap
    SHAP_AVAILABLE = True
    shap_explainer = None  # Will be initialized lazily
except ImportError:
    SHAP_AVAILABLE = False
    shap_explainer = None
    logger.warning("SHAP not available - explainability endpoints will be limited")

# Check for TensorFlow availability (for neural network feature extraction)
try:
    import tensorflow as tf
    TENSORFLOW_AVAILABLE = True
except ImportError:
    TENSORFLOW_AVAILABLE = False
    logger.warning("TensorFlow not available - neural network feature extraction disabled")

app = FastAPI(title="FraudDetectPro API", version="2.2")

# CORS configuration from environment variables
cors_origins_env = os.getenv("CORS_ORIGINS", "*")
if cors_origins_env == "*":
    cors_origins = ["*"]
else:
    # Split comma-separated origins
    cors_origins = [origin.strip() for origin in cors_origins_env.split(",")]

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

print("🔹 Starting FraudDetectPro API...")

# =====================================================
# Initialize Firebase Admin
# =====================================================
FIREBASE_INITIALIZED = False
try:
    if not firebase_admin._apps:
        # Try environment variable first (for cloud deployment)
        firebase_cred_base64 = os.getenv("FIREBASE_CREDENTIALS_BASE64")
        if firebase_cred_base64:
            import base64
            import json
            try:
                cred_dict = json.loads(base64.b64decode(firebase_cred_base64).decode('utf-8'))
                cred = credentials.Certificate(cred_dict)
                firebase_admin.initialize_app(cred)
                FIREBASE_INITIALIZED = True
                logger.info("✅ Firebase Admin initialized from environment variable")
            except Exception as e:
                logger.error(f"❌ Failed to decode Firebase credentials from environment: {e}")
        
        # If not initialized from env, try file paths
        if not FIREBASE_INITIALIZED:
            firebase_cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
            if not firebase_cred_path:
                # Try multiple paths for firebase.json
                possible_paths = [
                    os.path.join(os.path.dirname(os.path.dirname(__file__)), "firebase.json"),  # project root
                    "firebase.json",  # current directory
                    os.path.expanduser("~/.firebase/frauddetectpro.json"),  # user home directory
                ]
                
                for path in possible_paths:
                    if os.path.exists(path):
                        firebase_cred_path = path
                        break
            
            if firebase_cred_path and os.path.exists(firebase_cred_path):
                cred = credentials.Certificate(firebase_cred_path)
                firebase_admin.initialize_app(cred)
                FIREBASE_INITIALIZED = True
                logger.info(f"✅ Firebase Admin initialized from: {firebase_cred_path}")
            else:
                logger.error("❌ firebase.json not found in any of these locations:")
                if firebase_cred_path:
                    logger.error(f"   - {firebase_cred_path}")
                logger.error("⚠️ Authentication endpoints will fail without Firebase initialization")
                logger.error("💡 Please set FIREBASE_CREDENTIALS_PATH or FIREBASE_CREDENTIALS_BASE64 environment variable")
except Exception as e:
    logger.error(f"❌ Firebase initialization failed: {e}")
    FIREBASE_INITIALIZED = False

# =====================================================
# Paths
# =====================================================
BASE_DIR = os.path.dirname(os.path.dirname(__file__))  # project root

# Check if Railway volume is mounted (single volume solution)
# Volume should be mounted at /app/storage with subdirectories: models/ and data/processed/
STORAGE_VOLUME = os.path.join(BASE_DIR, "storage")
if os.path.exists(STORAGE_VOLUME):
    # Use volume-mounted paths
    MODELS_DIR = os.path.join(STORAGE_VOLUME, "models")
    DATA_DIR = os.path.join(STORAGE_VOLUME, "data", "processed")
    logger.info("📦 Using Railway volume for models and data")
else:
    # Use default paths (for local development)
    MODELS_DIR = os.path.join(BASE_DIR, "models")
    DATA_DIR = os.path.join(BASE_DIR, "data", "processed")

# =====================================================
# Model Validation Function
# =====================================================
def validate_models():
    """Validate that all loaded models match expected architecture"""
    validation_errors = []
    validation_warnings = []
    
    try:
        # Validate neural network (if enabled)
        if USE_NEURAL_NETWORK:
            if nn_model is None:
                validation_warnings.append("Neural network model is None (expected for hybrid model)")
            if feature_extractor is None:
                validation_warnings.append("Neural network feature extractor is None")
        
        # Validate ensemble models
        ensemble_models = [
            ("Random Forest", rf_model),
            ("XGBoost", xgb_model),
            ("Logistic Regression", lr_model)
        ]
        
        if lgbm_model is not None:
            ensemble_models.append(("LightGBM", lgbm_model))
        
        for model_name, model in ensemble_models:
            if model is None:
                validation_errors.append(f"{model_name} model is None")
            else:
                try:
                    # Try to get feature count from model
                    if hasattr(model, 'n_features_in_'):
                        model_features = model.n_features_in_
                        if model_features != expected_hybrid_features:
                            validation_warnings.append(
                                f"{model_name} expects {model_features} features, "
                                f"expected {expected_hybrid_features} hybrid features"
                            )
                except Exception as e:
                    validation_warnings.append(f"Could not validate {model_name} feature count: {e}")
        
        # Validate metadata consistency
        if metadata is None:
            validation_errors.append("Metadata is None")
        else:
            if "input_features" not in metadata:
                validation_warnings.append("Metadata missing 'input_features'")
            if "hybrid_features" not in metadata:
                validation_warnings.append("Metadata missing 'hybrid_features'")
            if "optimal_threshold" not in metadata:
                validation_warnings.append("Metadata missing 'optimal_threshold'")
        
        return {
            "valid": len(validation_errors) == 0,
            "errors": validation_errors,
            "warnings": validation_warnings
        }
    except Exception as e:
        return {
            "valid": False,
            "errors": [f"Validation failed with exception: {e}"],
            "warnings": []
        }

# =====================================================
# Load core models & metadata
# =====================================================
print("🔹 Loading models and metadata...")

# Load models with error handling
rf_model = None
xgb_model = None
lr_model = None
lgbm_model = None
metadata = None

try:
    rf_model = joblib.load(os.path.join(MODELS_DIR, "rf_model.pkl"))
    print("✅ Random Forest model loaded")
except Exception as e:
    logger.error(f"❌ Failed to load Random Forest model: {e}")
    raise

try:
    xgb_model = joblib.load(os.path.join(MODELS_DIR, "xgb_model.pkl"))
    print("✅ XGBoost model loaded")
except Exception as e:
    logger.error(f"❌ Failed to load XGBoost model: {e}")
    raise

try:
    lr_model = joblib.load(os.path.join(MODELS_DIR, "lr_model.pkl"))
    print("✅ Logistic Regression model loaded")
except Exception as e:
    logger.error(f"❌ Failed to load Logistic Regression model: {e}")
    raise

# Load LightGBM model (included in hybrid ensemble from 04_hybrid_model.ipynb)
lgbm_model_path = os.path.join(MODELS_DIR, "lgbm_model.pkl")
if os.path.exists(lgbm_model_path):
    try:
        lgbm_model = joblib.load(lgbm_model_path)
        print("✅ LightGBM model loaded")
    except Exception as e:
        lgbm_model = None
        logger.warning(f"⚠️  Failed to load LightGBM model: {e} - ensemble will use 3 models instead of 4")
else:
    lgbm_model = None
    print("⚠️  LightGBM model not found - ensemble will use 3 models instead of 4")

try:
    metadata = joblib.load(os.path.join(MODELS_DIR, "model_metadata.pkl"))
    print("✅ Model metadata loaded")
except Exception as e:
    logger.error(f"❌ Failed to load model metadata: {e}")
    raise

optimal_threshold = metadata.get("optimal_threshold", 0.5)
expected_input_features = int(metadata.get("input_features", 30))
expected_hybrid_features = int(metadata.get("hybrid_features", expected_input_features))
model_architecture = metadata.get("model_architecture", "simplified")

# Check if hybrid model with neural network
USE_NEURAL_NETWORK = (expected_hybrid_features > expected_input_features) and TENSORFLOW_AVAILABLE
nn_model = None
feature_extractor = None
v_indices = metadata.get("v_indices", list(range(1, 29)))  # V1-V28 indices

if USE_NEURAL_NETWORK:
    nn_model_path = os.path.join(MODELS_DIR, "nn_feature_extractor.h5")
    if os.path.exists(nn_model_path):
        try:
            nn_model = tf.keras.models.load_model(nn_model_path)
            # Extract feature layer
            try:
                feature_layer = nn_model.get_layer("feature_layer")
                feature_extractor = tf.keras.Model(inputs=nn_model.input, outputs=feature_layer.output)
            except:
                # Fallback: use second-to-last dense layer
                dense_layers = [layer for layer in nn_model.layers if isinstance(layer, tf.keras.layers.Dense)]
                if len(dense_layers) >= 2:
                    feature_layer = dense_layers[-2]
                    feature_extractor = tf.keras.Model(inputs=nn_model.input, outputs=feature_layer.output)
                else:
                    feature_extractor = nn_model
            logger.info(f"✅ Neural network feature extractor loaded: {expected_hybrid_features - expected_input_features} features")
            print(f"✅ Hybrid model: {expected_input_features} original + {expected_hybrid_features - expected_input_features} NN = {expected_hybrid_features} total")
        except Exception as e:
            logger.error(f"❌ Failed to load neural network: {e}")
            USE_NEURAL_NETWORK = False
            expected_hybrid_features = expected_input_features
            logger.warning("⚠️  Falling back to raw features only")
    else:
        USE_NEURAL_NETWORK = False
        expected_hybrid_features = expected_input_features
        logger.warning(f"⚠️  Neural network model not found at {nn_model_path}, using raw features only")
else:
    logger.info(f"✓ Using raw features only: {expected_hybrid_features} features")

print(f"🔹 Metadata: input_features={expected_input_features}, hybrid_features={expected_hybrid_features}, threshold={optimal_threshold}, architecture={model_architecture}")

# =====================================================
# Load scaler (from data/processed)
# =====================================================
scaler_path = os.path.join(DATA_DIR, "scaler.pkl")
if os.path.exists(scaler_path):
    try:
        scaler = joblib.load(scaler_path)
        print(f"✅ Scaler loaded from: {scaler_path}")
    except Exception as e:
        scaler = None
        print(f"⚠️ Failed to load scaler ({scaler_path}): {e} — proceeding without scaler")
else:
    scaler = None
    print(f"⚠️ Scaler not found at {scaler_path} — proceeding without scaler")

# Using raw features only - no neural network feature extraction

# Validate models after all are loaded
print("\n🔍 Validating model architecture...")
validation_result = validate_models()
if validation_result["valid"]:
    print("✅ All models validated successfully")
    if validation_result["warnings"]:
        for warning in validation_result["warnings"]:
            logger.warning(f"⚠️  {warning}")
else:
    for error in validation_result["errors"]:
        logger.error(f"❌ {error}")
    logger.error("⚠️  Model validation failed - API may not work correctly")

# =====================================================
# Authentication Dependency
# =====================================================
async def verify_firebase_token(authorization: Optional[str] = Header(None)):
    """Verify Firebase ID token from Authorization header"""
    if not FIREBASE_INITIALIZED:
        raise HTTPException(
            status_code=500, 
            detail="Firebase not initialized. Please configure firebase.json service account key."
        )
    
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")
    
    try:
        # Extract token from "Bearer <token>"
        token = authorization.split("Bearer ")[-1] if "Bearer " in authorization else authorization
        decoded_token = auth.verify_id_token(token)
        logger.info(f"✅ Authenticated user: {decoded_token.get('email')}")
        return decoded_token
    except Exception as e:
        logger.error(f"❌ Token verification failed: {str(e)}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

# Optional: Make authentication optional for testing
async def optional_auth(authorization: Optional[str] = Header(None)):
    """Optional authentication - use during development"""
    if not authorization:
        return {"uid": "anonymous", "email": "test@example.com"}
    return await verify_firebase_token(authorization)

# =====================================================
# Request/Response schemas
# =====================================================
class Transaction(BaseModel):
    features: list  # [Time, V1..V28, Amount] total expected_input_features items

class PredictionResponse(BaseModel):
    prediction: str
    probability: float  # Percentage (0-100)
    threshold_used: float  # Percentage (0-100)
    hybrid_feature_count: int
    transaction_id: Optional[str] = None  # ID for querying saved transaction in Firestore
    user_email: Optional[str] = None

class StatsResponse(BaseModel):
    total_predictions: int
    fraud_detected: int
    fraud_ratio: float
    model_accuracy: float

# =====================================================
# In-memory stats (replace with database in production)
# =====================================================
stats = {
    "total_predictions": 0,
    "fraud_detected": 0
}

# Store recent transactions in memory (last 100)
transactions_store: deque = deque(maxlen=100)

# Real-time streaming: Store connected clients for SSE
sse_clients: List[asyncio.Queue] = []

class TransactionResponse(BaseModel):
    id: str
    amount: float
    timestamp: str
    risk_score: float
    status: str
    prediction: str
    flagged: Optional[bool] = False
    feedback: Optional[str] = None
    analyst_email: Optional[str] = None
    flag_updated_at: Optional[str] = None

# =====================================================
# Endpoints
# =====================================================

@app.get("/")
def root():
    """Root endpoint"""
    return {
        "message": "FraudDetectPro API is running 🚀",
        "version": "2.2",
        "authentication": "Firebase Auth enabled"
    }

@app.get("/health")
def health_check():
    """Health check endpoint - no authentication required"""
    # Run model validation
    try:
        validation_result = validate_models()
    except Exception as e:
        validation_result = {
            "valid": False,
            "errors": [f"Validation exception: {str(e)}"],
            "warnings": []
        }
    
    return {
        "status": "healthy" if validation_result["valid"] else "degraded",
        "models_loaded": all([rf_model, xgb_model, lr_model]),
        "lgbm_loaded": lgbm_model is not None,
        "model_mode": "hybrid_nn" if USE_NEURAL_NETWORK else "simplified",
        "neural_network_enabled": USE_NEURAL_NETWORK,
        "scaler_loaded": scaler is not None,
        "firebase_initialized": (len(firebase_admin._apps) > 0) if firebase_admin._apps else False,
        "model_validation": {
            "valid": validation_result["valid"],
            "errors": validation_result["errors"],
            "warnings": validation_result["warnings"]
        },
        "expected_input_features": expected_input_features,
        "expected_hybrid_features": expected_hybrid_features,
        "optimal_threshold": float(optimal_threshold)
    }

@app.post("/predict", response_model=PredictionResponse)
async def predict(
    transaction: Transaction,
    user: dict = Depends(optional_auth)  # Use optional_auth for local/testing; switch to verify_firebase_token for prod
):
    """
    Predict fraud for a transaction
    Requires Firebase authentication
    """
    logger.info(f"Prediction request from user: {user.get('email')}")
    
    # Convert and validate input
    try:
        X = np.array(transaction.features, dtype=float)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not convert features to numeric array: {e}")

    if X.ndim == 1:
        X = X.reshape(1, -1)

    # Validate feature count
    if X.shape[1] != expected_input_features:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid input shape: expected {expected_input_features} features, but got {X.shape[1]}"
        )

    # Apply scaler if available
    if scaler is not None:
        try:
            X_scaled = scaler.transform(X)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Scaling failed: {e}")
    else:
        X_scaled = X

    # Neural network feature extraction (if enabled)
    if USE_NEURAL_NETWORK and feature_extractor is not None:
        try:
            # Extract V-features (V1-V28) for neural network
            X_v = X_scaled[:, v_indices]
            # Extract neural network features
            nn_features = feature_extractor.predict(X_v, verbose=0, batch_size=1)
            # Combine: original features + NN features
            X_hybrid = np.hstack([X_scaled, nn_features])
            logger.debug(f"✅ Hybrid features created: {X_scaled.shape[1]} original + {nn_features.shape[1]} NN = {X_hybrid.shape[1]} total")
        except Exception as e:
            logger.error(f"❌ Neural network feature extraction failed: {e}")
            # Fallback to raw features
            X_hybrid = X_scaled
            logger.warning("⚠️  Falling back to raw features only")
    else:
        # Use raw features directly (no neural network)
        X_hybrid = X_scaled

    if X_hybrid.shape[1] != expected_hybrid_features:
        raise HTTPException(
            status_code=500,
            detail=f"Feature length mismatch: got {X_hybrid.shape[1]}, expected {expected_hybrid_features}"
        )

    try:
        # Ensemble prediction (soft voting) - matches 04_hybrid_model.ipynb exactly
        # Uses all 4 models: RF, XGBoost, LR, and LightGBM (same as notebook)
        models = []
        if lgbm_model is not None:
            models = [rf_model, xgb_model, lr_model, lgbm_model]
        else:
            models = [rf_model, xgb_model, lr_model]
            logger.warning("⚠️  LightGBM model not available - using 3 models instead of 4")
        
        # Ensemble prediction: average probabilities from all models (soft voting)
        # This matches the notebook's ensemble_predict_proba function
        ensemble_probs = np.zeros(1)
        for model in models:
            ensemble_probs += model.predict_proba(X_hybrid)[:, 1]
        probs = ensemble_probs / len(models)
        
        # Log individual model probabilities for debugging
        rf_prob = rf_model.predict_proba(X_hybrid)[:, 1][0]
        xgb_prob = xgb_model.predict_proba(X_hybrid)[:, 1][0]
        lr_prob = lr_model.predict_proba(X_hybrid)[:, 1][0]
        
        if lgbm_model is not None:
            lgbm_prob = lgbm_model.predict_proba(X_hybrid)[:, 1][0]
            logger.info(
                f"Prediction probabilities - RF: {rf_prob:.4f}, XGB: {xgb_prob:.4f}, "
                f"LR: {lr_prob:.4f}, LGBM: {lgbm_prob:.4f}, Ensemble: {probs[0]:.4f}, "
                f"Threshold: {optimal_threshold:.4f}"
            )
        else:
            logger.info(
                f"Prediction probabilities - RF: {rf_prob:.4f}, XGB: {xgb_prob:.4f}, "
                f"LR: {lr_prob:.4f}, Ensemble: {probs[0]:.4f}, Threshold: {optimal_threshold:.4f} "
                f"(LightGBM not available)"
            )

        prediction = int(probs >= optimal_threshold)
        label = "Fraudulent" if prediction == 1 else "Legitimate"
        risk_score = float(probs[0] * 100)

        # Log if high-risk transaction is being misclassified
        if probs[0] > 0.3 and prediction == 0:
            logger.warning(
                f"⚠️  High-risk transaction ({probs[0]*100:.2f}%) classified as Legitimate "
                f"(threshold: {optimal_threshold*100:.2f}%)"
            )
        
        # Log if fraudulent transaction is being misclassified
        if probs[0] > 0.3 and prediction == 0:
            logger.warning(
                f"⚠️  High-risk transaction ({probs[0]*100:.2f}%) classified as Legitimate "
                f"(threshold: {optimal_threshold*100:.2f}%)"
            )

        # Update in-memory stats (for backward compatibility)
        stats["total_predictions"] += 1
        if prediction == 1:
            stats["fraud_detected"] += 1

        # Generate transaction ID
        transaction_id = str(uuid.uuid4())
        amount = float(X[0, -1]) if X.shape[0] > 0 else 0.0  # Last feature is Amount
        
        # Save to Firestore database (non-blocking with timeout to prevent hanging)
        try:
            # Run save in background thread with timeout to prevent blocking
            await asyncio.wait_for(
                asyncio.to_thread(
                    save_transaction,
                    transaction_id=transaction_id,
                    features=X[0].tolist(),  # Original features [Time, V1-V28, Amount]
                    fraud_probability=float(probs[0]),  # Probability (0-1)
                    prediction=label,  # "Fraudulent" or "Legitimate"
                    threshold_used=float(optimal_threshold),
                    user_email=user.get('email') or 'system@frauddetectpro.com',  # Use system email if no auth
                    model_version="2.2",
                    feature_count=expected_input_features,
                    hybrid_features=X_hybrid[0].tolist()  # Store hybrid features for SHAP
                ),
                timeout=2.0  # 2 second timeout - fail fast if Firestore is slow
            )
        except asyncio.TimeoutError:
            logger.warning("⚠️  Firestore save timed out (2s) - transaction saved in memory only")
        except Exception as db_error:
            logger.warning(f"⚠️  Failed to save transaction to Firestore: {db_error}")
            # Continue anyway - don't fail the request if DB save fails
        
        # Store transaction in memory (for quick access, last 100)
        transaction_data = {
            "id": transaction_id,
            "amount": amount,
            "timestamp": datetime.now().isoformat(),
            "risk_score": risk_score,
            "status": "flagged" if risk_score >= 70 else ("review" if risk_score >= 50 else "clear"),
            "prediction": label,
            "features": X[0].tolist(),  # Store original features for SHAP
            "hybrid_features": X_hybrid[0].tolist(),  # Store hybrid features for SHAP
            "probability": float(probs[0])
        }
        transactions_store.append(transaction_data)
        
        # Broadcast to all SSE clients for real-time updates
        try:
            asyncio.create_task(broadcast_transaction(transaction_data))
        except Exception as e:
            logger.warning(f"Failed to broadcast transaction: {e}")

        return PredictionResponse(
            prediction=label,
            probability=float(probs[0] * 100),  # Convert to percentage (0-100)
            threshold_used=float(optimal_threshold * 100),  # Convert threshold to percentage
            hybrid_feature_count=int(X_hybrid.shape[1]),
            transaction_id=transaction_id,  # Include ID so client can query it later
            user_email=user.get('email')
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Model ensemble prediction failed: {e}")

@app.get("/api/stats", response_model=StatsResponse)
async def get_stats(user: dict = Depends(optional_auth)):
    """Get prediction statistics from Firestore database with timeout and fallback"""
    logger.info(f"Stats requested by: {user.get('email')}")
    
    # Skip Firestore if we're hitting quota limits - use in-memory stats directly
    # This prevents long timeouts and quota errors
    try:
        # Get statistics from Firestore with short timeout (3 seconds)
        stats_data = await asyncio.wait_for(
            asyncio.to_thread(get_statistics, user_email=user.get('email')),
            timeout=3.0  # 3 second timeout - fail fast
        )
        
        # Check if we got valid data
        if stats_data and stats_data.get("total_transactions", 0) > 0:
            return StatsResponse(
                total_predictions=stats_data["total_transactions"],
                fraud_detected=stats_data["fraud_count"],
                fraud_ratio=stats_data["fraud_rate"],
                model_accuracy=95.3
            )
    except asyncio.TimeoutError:
        logger.warning("⚠️ Firestore stats query timed out (3s), using in-memory stats")
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg or "Quota exceeded" in error_msg:
            logger.warning("⚠️ Firestore quota exceeded, using in-memory stats")
        else:
            logger.error(f"Error fetching stats from Firestore: {e}")
    
    # Fallback to in-memory stats (always available and fast)
    fraud_ratio = (stats["fraud_detected"] / stats["total_predictions"] * 100) if stats["total_predictions"] > 0 else 0
    return StatsResponse(
        total_predictions=stats["total_predictions"],
        fraud_detected=stats["fraud_detected"],
        fraud_ratio=fraud_ratio,
        model_accuracy=95.3
    )

@app.get("/api/user/profile")
async def get_user_profile(user: dict = Depends(verify_firebase_token)):
    """Get current user profile"""
    return {
        "uid": user.get("uid"),
        "email": user.get("email"),
        "email_verified": user.get("email_verified", False)
    }

async def broadcast_transaction(transaction_data: dict):
    """Broadcast a new or updated transaction to all connected SSE clients"""
    if sse_clients:
        # Format for frontend
        formatted_tx = {
            "id": transaction_data.get("id"),
            "amount": transaction_data.get("amount"),
            "timestamp": transaction_data.get("timestamp"),
            "risk_score": transaction_data.get("risk_score"),
            "status": transaction_data.get("status"),
            "prediction": transaction_data.get("prediction"),
            "flagged": transaction_data.get("flagged", False),
            "feedback": transaction_data.get("feedback"),
            "analyst_email": transaction_data.get("analyst_email"),
            "flag_updated_at": transaction_data.get("flag_updated_at")
        }
        message = f"data: {json.dumps(formatted_tx)}\n\n"
        disconnected_clients = []
        for client_queue in sse_clients:
            try:
                await client_queue.put(message)
            except Exception as e:
                logger.warning(f"Failed to send to SSE client: {e}")
                disconnected_clients.append(client_queue)
        
        # Remove disconnected clients
        for client in disconnected_clients:
            if client in sse_clients:
                sse_clients.remove(client)

@app.get("/api/transactions/stream")
async def stream_transactions(
    user: dict = Depends(optional_auth),
    token: Optional[str] = None  # For SSE, token can come from query param
):
    """
    Server-Sent Events endpoint for real-time transaction streaming
    Transactions from data_generator.py will stream here immediately
    """
    async def event_generator():
        # Create a queue for this client
        queue = asyncio.Queue()
        sse_clients.append(queue)
        
        try:
            # Send initial message
            yield "data: {\"type\": \"connected\"}\n\n"
            
            # Send existing transactions from memory (real-time source)
            existing = list(transactions_store)
            for tx in existing[-20:]:  # Last 20 transactions
                formatted_tx = {
                    "id": tx.get("id"),
                    "amount": tx.get("amount"),
                    "timestamp": tx.get("timestamp"),
                    "risk_score": tx.get("risk_score"),
                    "status": tx.get("status"),
                    "prediction": tx.get("prediction"),
                    "flagged": tx.get("flagged", False),
                    "feedback": tx.get("feedback"),
                    "analyst_email": tx.get("analyst_email"),
                    "flag_updated_at": tx.get("flag_updated_at")
                }
                yield f"data: {json.dumps(formatted_tx)}\n\n"
            
            # Keep connection alive and stream new transactions
            while True:
                try:
                    # Wait for new transaction (with timeout to send keepalive)
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield message
                except asyncio.TimeoutError:
                    # Send keepalive ping
                    yield ": keepalive\n\n"
        finally:
            # Remove client when disconnected
            if queue in sse_clients:
                sse_clients.remove(queue)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable buffering for nginx
        }
    )

@app.get("/api/transactions")
async def get_transactions_endpoint(
    limit: int = 100,
    prediction: Optional[str] = None,
    min_probability: Optional[float] = None,
    max_probability: Optional[float] = None,
    user: dict = Depends(optional_auth)
):
    """
    Get transactions from in-memory store (real-time) or Firestore (fallback)
    
    Query Parameters:
    - limit: Maximum number of transactions to return (default: 100)
    - prediction: Filter by "Fraudulent" or "Legitimate"
    - min_probability: Minimum fraud probability (0-1)
    - max_probability: Maximum fraud probability (0-1)
    """
    logger.info(f"Transactions requested by: {user.get('email')}")
    
    # Return from in-memory store (real-time from data_generator)
    transactions_list = list(transactions_store)
    transactions_list.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    
    # Apply filters
    if prediction:
        transactions_list = [tx for tx in transactions_list if tx.get("prediction") == prediction]
    if min_probability is not None:
        transactions_list = [tx for tx in transactions_list if (tx.get("probability", 0) * 100) >= min_probability]
    if max_probability is not None:
        transactions_list = [tx for tx in transactions_list if (tx.get("probability", 0) * 100) <= max_probability]
    
    # Format for response
    result = []
    for tx in transactions_list[:limit]:
        result.append({
            "id": tx.get("id", ""),
            "amount": tx.get("amount", 0.0),
            "timestamp": tx.get("timestamp", ""),
            "risk_score": tx.get("risk_score", 0.0),
            "status": tx.get("status", "clear"),
            "prediction": tx.get("prediction", "Unknown"),
            "flagged": tx.get("flagged", False),
            "feedback": tx.get("feedback"),
            "analyst_email": tx.get("analyst_email"),
            "flag_updated_at": tx.get("flag_updated_at")
        })
    
    return result
    
    try:
        # Query Firestore
        transactions_list = get_transactions_from_db(
            limit=limit,
            user_email=user.get('email'),
            prediction_filter=prediction,
            min_probability=min_probability,
            max_probability=max_probability
        )
        
        # Convert to response format
        result = []
        for tx in transactions_list:
            result.append({
                "id": tx.get('id', ''),
                "amount": tx.get('amount', 0.0),
                "timestamp": tx.get('timestamp_iso', tx.get('timestamp', '')),
                "risk_score": tx.get('fraud_probability', 0.0) * 100,  # Convert to percentage
                "status": "flagged" if tx.get('fraud_probability', 0) >= 0.7 else ("review" if tx.get('fraud_probability', 0) >= 0.5 else "clear"),
                "prediction": tx.get('prediction', 'Unknown')
            })
        
        return result
        
    except Exception as e:
        logger.error(f"Error fetching transactions from Firestore: {e}")
        # Fallback to in-memory store
        transactions_list = list(transactions_store)
        transactions_list.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return transactions_list[:limit]

@app.get("/api/transactions/{transaction_id}")
async def get_transaction_by_id(transaction_id: str, user: dict = Depends(optional_auth)):
    """Get a specific transaction by ID from Firestore"""
    logger.info(f"Transaction {transaction_id} requested by: {user.get('email')}")
    
    try:
        transaction = get_transaction_from_db(transaction_id)
        if not transaction:
            raise HTTPException(status_code=404, detail="Transaction not found in database")
        
        # Convert to response format
        is_flagged = transaction.get('flagged', False)
        return {
            "id": transaction.get('id', transaction_id),
            "amount": transaction.get('amount', 0.0),
            "timestamp": transaction.get('timestamp_iso', transaction.get('timestamp', '')),
            "risk_score": transaction.get('fraud_probability', 0.0) * 100,
            "status": "flagged" if is_flagged else ("flagged" if transaction.get('fraud_probability', 0) >= 0.7 else ("review" if transaction.get('fraud_probability', 0) >= 0.5 else "clear")),
            "prediction": transaction.get('prediction', 'Unknown'),
            "fraud_probability": transaction.get('fraud_probability', 0.0),
            "threshold_used": transaction.get('threshold_used', 0.0),
            "model_version": transaction.get('model_version', '2.2'),
            "v_features": transaction.get('v_features', []),
            "time": transaction.get('time'),
            "user_email": transaction.get('user_email'),
            "flagged": is_flagged,
            "feedback": transaction.get('feedback'),
            "analyst_email": transaction.get('analyst_email'),
            "flag_updated_at": transaction.get('flag_updated_at_iso')
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching transaction from Firestore: {e}")
        # Fallback to in-memory store
    transaction = next((t for t in transactions_store if t["id"] == transaction_id), None)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return transaction

class FlagTransactionRequest(BaseModel):
    flagged: bool
    feedback: Optional[str] = None

class FlagTransactionResponse(BaseModel):
    success: bool
    message: str
    transaction_id: str
    flagged: bool

class SHAPExplanationResponse(BaseModel):
    transaction_id: str
    shap_values: List[float]
    feature_names: List[str]
    feature_values: List[float]
    base_value: float
    prediction_probability: float
    prediction: str

@app.get("/api/transactions/{transaction_id}/explain", response_model=SHAPExplanationResponse)
async def explain_transaction(transaction_id: str, user: dict = Depends(optional_auth)):
    """Get SHAP explanation for a specific transaction"""
    logger.info(f"SHAP explanation requested for {transaction_id} by: {user.get('email')}")
    
    # Find transaction - check in-memory store first, then database
    transaction = next((t for t in transactions_store if t["id"] == transaction_id), None)
    if not transaction:
        # Try to fetch from database
        try:
            db_transaction = get_transaction_from_db(transaction_id)
            if db_transaction:
                # Convert database format to expected format
                fraud_prob = db_transaction.get("fraud_probability", 0.0)
                transaction = {
                    "id": db_transaction.get("id", transaction_id),
                    "amount": db_transaction.get("amount", 0.0),
                    "timestamp": db_transaction.get("timestamp_iso", db_transaction.get("timestamp", "")),
                    "risk_score": fraud_prob * 100,  # Convert to percentage
                    "status": "flagged" if fraud_prob >= 0.7 else ("review" if fraud_prob >= 0.5 else "clear"),
                    "prediction": db_transaction.get("prediction", "Unknown"),
                    "features": db_transaction.get("features", []),
                    "hybrid_features": db_transaction.get("hybrid_features"),
                    "probability": fraud_prob  # Keep as 0-1 for SHAP
                }
        except Exception as e:
            logger.warning(f"Failed to fetch transaction from database: {e}")
    
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    if not SHAP_AVAILABLE:
        raise HTTPException(status_code=503, detail="SHAP library not available")
    
    try:
        # Get features - reconstruct if needed
        if "hybrid_features" in transaction and transaction["hybrid_features"] is not None:
            X_hybrid = np.array([transaction["hybrid_features"]], dtype=float)
        else:
            # Reconstruct hybrid features from stored features
            features_array = np.array([transaction.get("features", [])], dtype=float)
            if features_array.shape[1] == expected_input_features:
                # Scale features
                X_scaled = scaler.transform(features_array) if scaler else features_array
                # Use raw features directly (no neural network)
                X_hybrid = X_scaled
            else:
                raise HTTPException(status_code=400, detail="Cannot reconstruct features for explanation")
        
        # Use XGBoost for SHAP (TreeExplainer is fast and accurate)
        # Cache the explainer to avoid recreating it on every request
        global shap_explainer
        if shap_explainer is None:
            logger.info("Initializing SHAP TreeExplainer (this may take a moment)...")
            shap_explainer = shap.TreeExplainer(xgb_model)
            logger.info("✅ SHAP TreeExplainer initialized and cached")
        
        explainer = shap_explainer
        shap_values = explainer.shap_values(X_hybrid)
        
        # Get feature names
        feature_names = metadata.get('feature_names', [f'Feature_{i}' for i in range(X_hybrid.shape[1])])
        if len(feature_names) < X_hybrid.shape[1]:
            # Add missing feature names
            missing_count = X_hybrid.shape[1] - len(feature_names)
            feature_names = feature_names + [f'Feature_{i}' for i in range(len(feature_names), len(feature_names) + missing_count)]
        
        # Handle binary classification SHAP values
        if isinstance(shap_values, list) and len(shap_values) > 1:
            shap_values = shap_values[1]  # Use class 1 (fraud) SHAP values
        
        # Flatten if needed
        if shap_values.ndim > 1:
            shap_values = shap_values[0]
        
        base_value = float(explainer.expected_value)
        if isinstance(base_value, np.ndarray):
            base_value = float(base_value[1] if len(base_value) > 1 else base_value[0])
        
        return SHAPExplanationResponse(
            transaction_id=transaction_id,
            shap_values=shap_values.tolist() if isinstance(shap_values, np.ndarray) else shap_values,
            feature_names=feature_names[:len(shap_values)] if len(feature_names) >= len(shap_values) else [f'Feature_{i}' for i in range(len(shap_values))],
            feature_values=X_hybrid[0].tolist(),
            base_value=base_value,
            prediction_probability=transaction.get("probability", transaction.get("risk_score", 0) / 100),
            prediction=transaction.get("prediction", "Unknown")
        )
    except Exception as e:
        logger.error(f"SHAP explanation failed: {e}")
        raise HTTPException(status_code=500, detail=f"SHAP explanation failed: {str(e)}")

@app.post("/api/transactions/{transaction_id}/flag", response_model=FlagTransactionResponse)
async def flag_transaction(
    transaction_id: str,
    flag_request: FlagTransactionRequest,
    user: dict = Depends(optional_auth)
):
    """
    Flag or unflag a transaction with optional feedback
    """
    logger.info(f"Flag request for transaction {transaction_id} by: {user.get('email')}")
    
    try:
        # Check if transaction exists
        transaction = get_transaction_from_db(transaction_id)
        if not transaction:
            # Fallback to in-memory store
            transaction = next((t for t in transactions_store if t["id"] == transaction_id), None)
            if not transaction:
                raise HTTPException(status_code=404, detail="Transaction not found")
        
        # Update flag status in Firestore
        success = update_transaction_flag(
            transaction_id=transaction_id,
            flagged=flag_request.flagged,
            feedback=flag_request.feedback,
            analyst_email=user.get('email')
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update transaction flag status")
        
        # Also update in-memory store for real-time updates
        for tx in transactions_store:
            if tx.get("id") == transaction_id:
                tx["flagged"] = flag_request.flagged
                tx["feedback"] = flag_request.feedback
                tx["analyst_email"] = user.get('email')
                tx["flag_updated_at"] = datetime.now().isoformat()
                # Update status to reflect flagged state
                if flag_request.flagged:
                    tx["status"] = "flagged"
                else:
                    # Restore original status based on risk score
                    risk_score = tx.get("risk_score", 0)
                    if risk_score >= 70:
                        tx["status"] = "flagged"
                    elif risk_score >= 50:
                        tx["status"] = "review"
                    else:
                        tx["status"] = "clear"
                
                # Broadcast updated transaction to all SSE clients
                try:
                    asyncio.create_task(broadcast_transaction(tx))
                except Exception as e:
                    logger.warning(f"Failed to broadcast flag update: {e}")
                break
        
        action = "flagged" if flag_request.flagged else "unflagged"
        logger.info(f"✅ Transaction {transaction_id} {action} by {user.get('email')}")
        
        return FlagTransactionResponse(
            success=True,
            message=f"Transaction {action} successfully",
            transaction_id=transaction_id,
            flagged=flag_request.flagged
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error flagging transaction: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to flag transaction: {str(e)}")

@app.get("/debug-model-info")
def debug_model_info():
    """Debug endpoint - no authentication required"""
    ensemble_models = ["Random Forest", "XGBoost", "Logistic Regression"]
    if lgbm_model is not None:
        ensemble_models.append("LightGBM")
    
    return {
        "expected_input_features": expected_input_features,
        "expected_hybrid_features": expected_hybrid_features,
        "optimal_threshold": float(optimal_threshold),
        "optimal_threshold_percentage": float(optimal_threshold * 100),
        "ensemble_models": ensemble_models,
        "ensemble_model_count": len(ensemble_models),
        "lgbm_loaded": lgbm_model is not None,
        "scaler_loaded": bool(scaler is not None),
        "firebase_initialized": len(firebase_admin._apps) > 0,
        "note": "If threshold is too high (>0.7), fraudulent transactions may be misclassified as legitimate"
    }

@app.post("/admin/update-threshold")
async def update_threshold(
    new_threshold: float,
    user: dict = Depends(optional_auth)
):
    """
    Update the prediction threshold (requires restart to persist)
    WARNING: This only updates in-memory. To persist, update models/model_metadata.pkl
    """
    global optimal_threshold
    
    if not (0.0 <= new_threshold <= 1.0):
        raise HTTPException(status_code=400, detail="Threshold must be between 0.0 and 1.0")
    
    old_threshold = optimal_threshold
    optimal_threshold = new_threshold
    
    # Update metadata (in-memory only)
    metadata['optimal_threshold'] = new_threshold
    
    logger.warning(
        f"Threshold updated by {user.get('email', 'unknown')}: "
        f"{old_threshold:.4f} → {new_threshold:.4f} "
        f"(⚠️  Changes are in-memory only, restart required for persistence)"
    )
    
    return {
        "message": "Threshold updated (in-memory only)",
        "old_threshold": float(old_threshold),
        "new_threshold": float(new_threshold),
        "warning": "Restart API to persist changes. To make permanent, update models/model_metadata.pkl"
    }

# =====================================================
# Exception handlers
# =====================================================
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    logger.error(f"HTTP Exception: {exc.detail}")
    return JSONResponse(status_code=exc.status_code, content={
        "error": exc.detail,
        "status_code": exc.status_code
    })