# FraudDetectPro: Technical Documentation

## Executive Summary

FraudDetectPro is a hybrid machine learning system for real-time credit card fraud detection, developed as part of a final year Informatics and Computer Science project at Strathmore University. The system integrates ensemble learning, neural network feature extraction, and explainable AI (XAI) to enhance accuracy, transparency, and trust in fraud detection.

## 1. Introduction

### 1.1 Problem Statement

Traditional fraud detection systems face several critical challenges:
- Extreme class imbalance (fraud represents less than 0.5% of transactions)
- High false positive rates, leading to poor customer experience
- Black-box machine learning models lacking interpretability for analysts and regulators
- Limited real-time processing capabilities

### 1.2 Solution Overview

FraudDetectPro addresses these challenges through:
- Two-stage hybrid model architecture combining neural networks and ensemble methods
- Supervised ensemble models (Logistic Regression, Random Forest, XGBoost, LightGBM)
- Neural network feature extraction for enhanced pattern recognition
- Explainability modules using SHAP for model transparency
- Real-time prediction API with sub-100ms response times
- Interactive web dashboard for fraud analysts

## 2. System Architecture

### 2.1 High-Level Architecture

The system follows a three-tier architecture:

```
┌─────────────────────────────────┐
│   Frontend Layer (React/TS)     │
│   - Dashboard                    │
│   - Manual Prediction Interface │
│   - Transaction History          │
│   - Explainability Center        │
└──────────────┬──────────────────┘
               │ HTTP/REST API
               ↓
┌─────────────────────────────────┐
│   Backend Layer (FastAPI)       │
│   - Prediction Endpoints         │
│   - Authentication (Firebase)   │
│   - Transaction Management       │
└──────────────┬──────────────────┘
               │
    ┌──────────┴──────────┐
    ↓                     ↓
┌──────────┐        ┌──────────────┐
│ Firebase │        │ ML Model     │
│   Auth   │        │   Engine     │
└──────────┘        └──────────────┘
```

### 2.2 Component Layers

1. **Data Source Layer**: Kaggle Credit Card Fraud dataset with 30 input features
2. **Data Processing Layer**: Cleaning, normalization, SMOTE balancing, and feature engineering
3. **Machine Learning Layer**: Two-stage hybrid model with ensemble classifiers
4. **Explainability Layer**: SHAP-based feature importance analysis
5. **Application Layer**: REST API for predictions and transaction management
6. **User Interface Layer**: React-based web dashboard for fraud analysts
7. **Storage Layer**: In-memory storage for transactions and statistics

## 3. Machine Learning Architecture

### 3.1 Two-Stage Hybrid Model

The system employs a two-stage hybrid approach:

**Stage 1: Neural Network Feature Extraction**
- Input: 30 original features (Time, V1-V28, Amount)
- Architecture: Dense layers with dropout regularization
- Output: 32 extracted features capturing non-linear patterns
- Purpose: Deep pattern recognition and feature transformation

**Stage 2: Ensemble Classification**
- Input: 62 hybrid features (30 original + 32 extracted)
- Models: Random Forest, XGBoost, Logistic Regression, LightGBM
- Method: Soft voting ensemble (probability averaging)
- Output: Fraud probability score (0-100%)
- Threshold: 89.8% optimal threshold for binary classification

### 3.2 Model Training

- **Training Paradigm**: Stratified holdout validation
- **Train/Test Split**: 80/20 with stratification to preserve class distribution
- **Validation**: 20% of training data used for validation during training
- **Class Balancing**: SMOTE oversampling applied to training data
- **Hyperparameters**: Optimized through validation performance

### 3.3 Model Performance

Test set performance metrics:
- **Accuracy**: 99.94%
- **F1-Score**: 82.11%
- **ROC-AUC**: 95.11%
- **Precision**: 84.78%
- **Recall**: 79.59%

## 4. Technical Implementation

### 4.1 Technology Stack

**Backend:**
- Python 3.9+
- FastAPI 0.104+ (REST API framework)
- TensorFlow/Keras (Neural network models)
- Scikit-learn (Ensemble models)
- NumPy, Pandas (Data processing)
- Firebase Admin SDK (Authentication)

**Frontend:**
- React 18.3+
- TypeScript
- Vite (Build tool)
- React Router (Navigation)
- Tailwind CSS (Styling)
- Shadcn UI (Component library)
- Recharts (Data visualization)

**Machine Learning:**
- XGBoost
- LightGBM
- Scikit-learn (Random Forest, Logistic Regression)
- SHAP (Explainability)
- Imbalanced-learn (SMOTE)

### 4.2 Project Structure

```
frauddetectpro/
├── app/
│   ├── main.py                 # FastAPI backend application
│   └── models/                 # Trained ML model files
│       ├── nn_feature_extractor.h5
│       ├── rf_model.pkl
│       ├── xgb_model.pkl
│       ├── lr_model.pkl
│       ├── lgbm_model.pkl
│       └── model_metadata.pkl
├── Frontend/
│   ├── src/
│   │   ├── pages/              # React page components
│   │   │   ├── Index.tsx       # Landing page
│   │   │   ├── SignIn.tsx
│   │   │   ├── SignUp.tsx
│   │   │   ├── Dashboard.tsx
│   │   │   ├── ManualPrediction.tsx
│   │   │   └── ...
│   │   ├── components/        # Reusable UI components
│   │   ├── services/           # API service layer
│   │   └── config/             # Configuration files
│   └── package.json
├── notebooks/
│   ├── 03_data_prep.ipynb     # Data preprocessing
│   └── 04_hybrid_model.ipynb  # Model training
├── data/
│   └── processed/              # Preprocessed datasets
├── firebase.json               # Firebase service account key
├── requirements.txt            # Python dependencies
└── README.md
```

### 4.3 Data Storage

The system uses in-memory storage for development and testing:
- **Transactions**: Stored in Python deque with maximum 100 entries
- **Statistics**: Maintained in memory dictionary
- **Persistence**: Data is lost on server restart
- **Production Note**: Database integration recommended for production deployment

## 5. User Interface Features

### 5.1 Landing Page

The landing page (Index.tsx) provides:
- System overview and value proposition
- Feature highlights (Real-Time Detection, Explainable AI, Continuous Learning)
- Performance metrics display (Response Time)
- Navigation to sign-in and sign-up pages

### 5.2 Dashboard

The main dashboard includes:
- Real-time transaction monitoring with auto-refresh (5-second intervals)
- Key performance metrics:
  - Total Transactions
  - Fraud Cases Detected
  - Fraud Ratio
- Transaction risk distribution visualization (pie chart)
- Top high-risk transactions display
- Paginated transaction table with filtering

### 5.3 Manual Prediction Interface

The manual prediction page offers two modes:

**Single Transaction Prediction:**
- Form-based input for 30 transaction features
- Real-time prediction with probability scoring
- Visual risk indicators and threshold comparison
- Detailed prediction results display

**Batch CSV Upload:**
- CSV file upload with format validation
- Support for 30 or 31 columns (auto-handles Class column)
- Real-time parsing with progress indication
- Batch prediction processing with progress tracking
- Results table with downloadable CSV export
- Error handling for invalid rows

### 5.4 Navigation Structure

- Dashboard: Main overview and transaction monitoring
- Transactions: Transaction history and details
- Manual Prediction: Single and batch prediction interface
- Explainability: SHAP-based feature importance analysis
- Knowledge Base: System documentation and guides

## 6. API Documentation

### 6.1 Authentication

All API endpoints (except `/health` and `/`) require Firebase authentication via Bearer token:

```http
Authorization: Bearer <firebase_id_token>
```

### 6.2 Core Endpoints

#### Health Check
```http
GET /health
```

Returns system health status including model loading state and Firebase initialization status.

#### Predict Transaction
```http
POST /predict
Content-Type: application/json
Authorization: Bearer <token>

{
  "features": [0.0, -1.359807, -0.072781, ..., 149.62]
}
```

**Request:** Array of exactly 30 numeric features (Time, V1-V28, Amount)

**Response:**
```json
{
  "prediction": "Fraudulent" | "Legitimate",
  "probability": 87.5,
  "threshold_used": 89.8,
  "hybrid_feature_count": 62,
  "user_email": "user@example.com"
}
```

#### Get Statistics
```http
GET /api/stats
Authorization: Bearer <token>
```

**Response:**
```json
{
  "total_predictions": 1000,
  "fraud_detected": 15,
  "fraud_ratio": 1.5
}
```

#### Get Transactions
```http
GET /api/transactions?limit=100
Authorization: Bearer <token>
```

Returns list of recent transactions with risk scores and predictions.

#### Get Transaction Details
```http
GET /api/transactions/{transaction_id}
Authorization: Bearer <token>
```

Returns detailed information for a specific transaction including features and prediction explanation.

### 6.3 API Documentation

Interactive API documentation available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## 7. Installation and Setup

### 7.1 Prerequisites

- Python 3.9 or higher
- Node.js 18+ and npm
- Firebase account with project setup
- Git

### 7.2 Backend Setup

1. **Clone the repository**
```bash
git clone <repository-url>
cd frauddetectpro
```

2. **Set up Python environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. **Configure Firebase**
   - Create a Firebase project at Firebase Console
   - Generate service account key (JSON)
   - Save as `firebase.json` in project root
   - Enable Authentication methods (Email, Google, GitHub)

4. **Train and save models**
   - Execute notebooks in order: `03_data_prep.ipynb` then `04_hybrid_model.ipynb`
   - Models will be saved to `models/` directory

5. **Start the backend server**
```bash
cd app
uvicorn main:app --reload --port 8000
```

### 7.3 Frontend Setup

1. **Navigate to frontend directory**
```bash
cd Frontend
```

2. **Install dependencies**
```bash
npm install
```

3. **Configure environment**
   - Create `.env` file with:
   ```
   VITE_API_URL=http://localhost:8000
   ```

4. **Start development server**
```bash
npm run dev
```

5. **Build for production**
```bash
npm run build
```

### 7.4 Access Points

- Frontend Application: http://localhost:5173 (or port shown in terminal)
- Backend API: http://localhost:8000
- API Documentation: http://localhost:8000/docs

## 8. Usage Guide

### 8.1 User Registration and Authentication

1. Navigate to the landing page
2. Click "Get Started" or "Sign In"
3. Create account using:
   - Email and password
   - Google account
   - GitHub account
   - Phone number with OTP

### 8.2 Making Predictions

**Single Transaction:**
1. Navigate to Manual Prediction from the collapsible menu
2. Enter transaction features manually or use sample data
3. Click "Predict Fraud Risk"
4. Review prediction results with probability and risk score

**Batch Processing:**
1. Navigate to Manual Prediction page
2. Upload CSV file with transaction data
3. Ensure CSV has 30 features per row (or 31 with Class column)
4. Click "Predict All Transactions"
5. Monitor progress and review results
6. Download results as CSV if needed

### 8.3 Monitoring Transactions

1. Access Dashboard from navigation menu
2. View real-time transaction feed
3. Review risk distribution and statistics
4. Click on transactions for detailed analysis
5. Use explainability center for feature importance insights

## 9. Development and Testing

### 9.1 Development Workflow

1. Backend changes: Modify `app/main.py` and restart server
2. Frontend changes: Hot reload enabled in development mode
3. Model updates: Retrain using notebooks and update model files

### 9.2 Testing

**Backend Testing:**
```bash
pytest tests/
```

**Frontend Testing:**
```bash
cd Frontend
npm test
```

### 9.3 Code Quality

**Python:**
```bash
black app/
flake8 app/
```

**TypeScript:**
```bash
cd Frontend
npm run lint
```

## 10. Security Considerations

- Firebase Authentication with multiple provider support
- JWT token-based API access control
- Input validation and sanitization on all endpoints
- Secure credential management (firebase.json not committed)
- HTTPS recommended for production deployment
- Rate limiting recommended for production API

## 11. Performance Characteristics

- **Prediction Latency**: Sub-100ms average response time
- **Throughput**: Handles multiple concurrent requests
- **Scalability**: Stateless API design supports horizontal scaling
- **Storage**: In-memory storage suitable for development; database recommended for production

## 12. Limitations and Future Work

### 12.1 Current Limitations

- In-memory storage (data lost on restart)
- Maximum 100 transactions stored in memory
- No persistent transaction history
- Single-server deployment (no load balancing)

### 12.2 Recommended Enhancements

- Database integration (PostgreSQL, MongoDB, or Firestore)
- Persistent transaction storage and history
- Model retraining pipeline
- Real-time streaming data integration
- Advanced analytics and reporting
- Multi-user role management
- Audit logging and compliance features

## 13. References

- Kaggle Credit Card Fraud Detection Dataset
- FastAPI Documentation: https://fastapi.tiangolo.com/
- React Documentation: https://react.dev/
- Firebase Documentation: https://firebase.google.com/docs
- SHAP Documentation: https://shap.readthedocs.io/

