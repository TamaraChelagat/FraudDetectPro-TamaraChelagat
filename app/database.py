"""
Database module for storing transactions and predictions
Uses Firestore (Google Cloud) for scalable storage
"""

from datetime import datetime
from typing import List, Dict, Optional
import logging
import firebase_admin
from firebase_admin import firestore

logger = logging.getLogger(__name__)

# Global database client (lazy initialization)
_db_client = None

def get_db():
    """Get Firestore database client (lazy initialization)
    Uses 'frauddetectpro' database instead of default
    """
    global _db_client
    if not firebase_admin._apps:
        raise RuntimeError("Firebase Admin not initialized. Please initialize Firebase first.")
    if _db_client is None:
        # Use named database 'frauddetectpro' instead of '(default)'
        try:
            _db_client = firestore.client(database_id='frauddetectpro')
        except Exception as e:
            # Fallback to default database if named database doesn't exist
            logger.warning(f"⚠️  Named database 'frauddetectpro' not found, using default database: {e}")
            _db_client = firestore.client()
    return _db_client

def init_database():
    """Initialize database (Firestore automatically creates collections on first write)"""
    try:
        db = get_db()
        # Test connection by reading from a test collection
        _ = db.collection('_health').limit(1).stream()
        logger.info("✅ Firestore database connection initialized")
    except Exception as e:
        logger.warning(f"⚠️  Firestore initialization check failed (may work on first write): {e}")

def save_transaction(
    transaction_id: str,
    features: List[float],
    fraud_probability: float,
    prediction: str,
    threshold_used: float,
    user_email: Optional[str] = None,
    model_version: str = "2.2",
    feature_count: int = 30,
    hybrid_features: Optional[List[float]] = None
) -> bool:
    """
    Save a transaction and its prediction to Firestore
    
    Args:
        transaction_id: Unique transaction ID
        features: List of 30 features [Time, V1-V28, Amount]
        fraud_probability: Probability of fraud (0-1)
        prediction: "Fraudulent" or "Legitimate"
        threshold_used: Threshold used for prediction
        user_email: Email of user making the request
        model_version: Version of the model used
        feature_count: Number of features
    
    Returns:
        bool: True if successful
    """
    try:
        db = get_db()
        
        # Extract features
        time_val = features[0] if len(features) > 0 else None
        amount_val = features[-1] if len(features) > 0 else None
        v_features = features[1:29] if len(features) >= 29 else []  # V1-V28
        
        # Prepare transaction document
        transaction_data = {
            'timestamp': firestore.SERVER_TIMESTAMP,
            'timestamp_iso': datetime.now().isoformat(),
            'user_email': user_email,
            
            # Transaction features
            'time': time_val,
            'amount': amount_val,
            'v_features': v_features,  # List of V1-V28 values
            'features': features,  # Full feature array for SHAP reconstruction
            'hybrid_features': hybrid_features,  # Hybrid features if available (for SHAP)
            
            # Prediction results
            'fraud_probability': fraud_probability,
            'prediction': prediction,
            'threshold_used': threshold_used,
            'risk_score': fraud_probability * 100,  # Also store as percentage for compatibility
            
            # Model metadata
            'model_version': model_version,
            'feature_count': feature_count,
            
            # Additional metadata
            'created_at': firestore.SERVER_TIMESTAMP
        }
        
        # Save to Firestore
        doc_ref = db.collection('transactions').document(transaction_id)
        doc_ref.set(transaction_data)
        
        logger.info(f"✅ Transaction {transaction_id} saved to Firestore")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error saving transaction to Firestore: {e}")
        return False


def get_transaction(transaction_id: str) -> Optional[Dict]:
    """Get a single transaction by ID"""
    try:
        db = get_db()
        doc_ref = db.collection('transactions').document(transaction_id)
        doc = doc_ref.get()
        
        if doc.exists:
            data = doc.to_dict()
            data['id'] = doc.id
            return data
        return None
        
    except Exception as e:
        logger.error(f"❌ Error fetching transaction from Firestore: {e}")
        return None


def get_transactions(
    limit: int = 100,
    offset: int = 0,
    user_email: Optional[str] = None,
    prediction_filter: Optional[str] = None,
    min_probability: Optional[float] = None,
    max_probability: Optional[float] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> List[Dict]:
    """
    Get transactions with filtering options
    
    Args:
        limit: Maximum number of transactions to return
        offset: Offset for pagination (Firestore uses cursor-based pagination)
        user_email: Filter by user email
        prediction_filter: "Fraudulent" or "Legitimate"
        min_probability: Minimum fraud probability
        max_probability: Maximum fraud probability
        start_date: Start date (ISO format)
        end_date: End date (ISO format)
    
    Returns:
        List of transaction dictionaries
    """
    try:
        db = get_db()
        
        # Fetch transactions: user's transactions + system transactions (user_email=None)
        # This allows data generator transactions to be visible to all users
        all_transactions = []
        
        # Simplified approach: Fetch all transactions and filter in memory
        # This avoids needing composite indexes for user_email + timestamp queries
        query = db.collection('transactions')
        
        # Apply filters that don't require composite indexes
        if prediction_filter:
            query = query.where('prediction', '==', prediction_filter)
        
        if min_probability is not None:
            query = query.where('fraud_probability', '>=', min_probability)
        
        if max_probability is not None:
            query = query.where('fraud_probability', '<=', max_probability)
        
        if start_date:
            query = query.where('timestamp_iso', '>=', start_date)
        
        if end_date:
            query = query.where('timestamp_iso', '<=', end_date)
        
        # Fetch all matching documents (limit to reasonable number)
        # Note: We filter by user_email in memory to avoid index requirements
        docs = query.limit(1000).stream()  # Get up to 1000 transactions
        
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            
            # Filter by user_email in memory (if provided)
            # Show user's transactions AND system transactions
            doc_user_email = data.get('user_email')
            
            if user_email:
                # Include user's transactions and system transactions
                if doc_user_email == user_email or doc_user_email == 'system@frauddetectpro.com':
                    all_transactions.append(data)
            else:
                # No user_email provided - include all
                all_transactions.append(data)
        
        # Sort all transactions by timestamp (most recent first) and limit
        all_transactions.sort(key=lambda x: x.get('timestamp_iso', x.get('timestamp', '')), reverse=True)
        transactions = all_transactions[:limit]
        
        return transactions
        
    except Exception as e:
        logger.error(f"❌ Error fetching transactions from Firestore: {e}")
        return []


def get_statistics(
    user_email: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> Dict:
    """
    Get statistics about stored transactions
    
    Returns:
        Dictionary with statistics
    """
    try:
        db = get_db()
        query = db.collection('transactions')
        
        # Apply filters
        if user_email:
            query = query.where('user_email', '==', user_email)
        
        if start_date:
            query = query.where('timestamp_iso', '>=', start_date)
        
        if end_date:
            query = query.where('timestamp_iso', '<=', end_date)
        
        # Get all matching documents with timeout protection
        # Limit to reasonable number to avoid quota issues
        docs = list(query.limit(10000).stream())  # Cap at 10k to prevent quota issues
        total = len(docs)
        
        if total == 0:
            return {
                "total_transactions": 0,
                "fraud_count": 0,
                "legitimate_count": 0,
                "fraud_rate": 0.0,
                "average_fraud_probability": 0.0,
                "average_amount": 0.0
            }
        
        # Calculate statistics
        fraud_count = 0
        total_probability = 0.0
        total_amount = 0.0
        amount_count = 0
        
        for doc in docs:
            data = doc.to_dict()
            
            if data.get('prediction') == 'Fraudulent':
                fraud_count += 1
            
            prob = data.get('fraud_probability')
            if prob is not None:
                total_probability += prob
            
            amount = data.get('amount')
            if amount is not None:
                total_amount += amount
                amount_count += 1
        
        return {
            "total_transactions": total,
            "fraud_count": fraud_count,
            "legitimate_count": total - fraud_count,
            "fraud_rate": (fraud_count / total * 100) if total > 0 else 0.0,
            "average_fraud_probability": (total_probability / total) if total > 0 else 0.0,
            "average_amount": (total_amount / amount_count) if amount_count > 0 else 0.0
        }
        
    except Exception as e:
        logger.error(f"❌ Error fetching statistics from Firestore: {e}")
        return {
            "total_transactions": 0,
            "fraud_count": 0,
            "legitimate_count": 0,
            "fraud_rate": 0.0,
            "average_fraud_probability": 0.0,
            "average_amount": 0.0
        }


def update_transaction_flag(
    transaction_id: str,
    flagged: bool,
    feedback: Optional[str] = None,
    analyst_email: Optional[str] = None
) -> bool:
    """
    Update the flag status of a transaction
    
    Args:
        transaction_id: Unique transaction ID
        flagged: True to flag, False to unflag
        feedback: Optional feedback/reason from analyst
        analyst_email: Email of analyst who flagged/unflagged
    
    Returns:
        bool: True if successful
    """
    try:
        db = get_db()
        doc_ref = db.collection('transactions').document(transaction_id)
        
        # Check if transaction exists
        doc = doc_ref.get()
        if not doc.exists:
            logger.error(f"❌ Transaction {transaction_id} not found")
            return False
        
        # Prepare update data
        update_data = {
            'flagged': flagged,
            'flag_updated_at': firestore.SERVER_TIMESTAMP,
            'flag_updated_at_iso': datetime.now().isoformat()
        }
        
        if feedback is not None:
            update_data['feedback'] = feedback
        
        if analyst_email is not None:
            update_data['analyst_email'] = analyst_email
        
        # If unflagging, clear feedback
        if not flagged:
            update_data['feedback'] = None
        
        # Update document
        doc_ref.update(update_data)
        
        action = "flagged" if flagged else "unflagged"
        logger.info(f"✅ Transaction {transaction_id} {action} by {analyst_email}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error updating transaction flag status: {e}")
        return False


# Database will be initialized when first used (lazy initialization)
# This allows the API to start even if Firebase isn't configured yet
logger.info("📦 Database module loaded (Firestore connection will be initialized on first use)")
