import axios, { AxiosInstance, AxiosError } from 'axios';
import { auth } from '../config/firebase';
import { API_CONFIG } from '../config/api';

// Create axios instance
const api: AxiosInstance = axios.create({
  baseURL: API_CONFIG.baseURL,
  timeout: API_CONFIG.timeout,
  headers: API_CONFIG.headers
});

// Add Firebase token to all requests
api.interceptors.request.use(async (config) => {
  const user = auth.currentUser;
  if (user) {
    try {
      const token = await user.getIdToken();
      config.headers.Authorization = `Bearer ${token}`;
    } catch (error) {
      console.error('Failed to get auth token:', error);
    }
  }
  return config;
});

// Handle errors
api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      console.error('Unauthorized - redirecting to login');
      // You can add redirect logic here if needed
    }
    return Promise.reject(error);
  }
);

// API Response Types
export interface PredictionResponse {
  prediction: 'Fraudulent' | 'Legitimate';
  probability: number;  // Percentage (0-100)
  threshold_used: number;  // Percentage (0-100)
  hybrid_feature_count: number;
  transaction_id?: string;  // ID for querying saved transaction and SHAP explanation
  user_email?: string;
}

export interface StatsResponse {
  total_predictions: number;
  fraud_detected: number;
  fraud_ratio: number;
  model_accuracy: number;
}

export interface HealthResponse {
  status: string;
  models_loaded: boolean;
  scaler_loaded: boolean;
  firebase_initialized: boolean;
}

export interface TransactionResponse {
  id: string;
  amount: number;
  timestamp: string;
  risk_score: number;
  status: string;
  prediction: string;
  features?: number[];
  hybrid_features?: number[];
  probability?: number;
  flagged?: boolean;
  feedback?: string;
  analyst_email?: string;
  flag_updated_at?: string;
}

export interface FlagTransactionRequest {
  flagged: boolean;
  feedback?: string;
}

export interface FlagTransactionResponse {
  success: boolean;
  message: string;
  transaction_id: string;
  flagged: boolean;
}

export interface SHAPExplanationResponse {
  transaction_id: string;
  shap_values: number[];
  feature_names: string[];
  feature_values: number[];
  base_value: number;
  prediction_probability: number;
  prediction: string;
}

// API Service
export const apiService = {
  // Health check (no auth needed)
  async checkHealth(): Promise<HealthResponse> {
    const response = await api.get<HealthResponse>('/health');
    return response.data;
  },

  // Get prediction statistics
  async getStats(): Promise<StatsResponse> {
    const response = await api.get<StatsResponse>('/api/stats');
    return response.data;
  },

  // Predict transaction fraud
  // features: [Time, V1, V2, ..., V28, Amount] - exactly 30 numbers
  async predictTransaction(features: number[]): Promise<PredictionResponse> {
    if (features.length !== 30) {
      throw new Error(`Expected 30 features, got ${features.length}`);
    }
    const response = await api.post<PredictionResponse>('/predict', {
      features
    });
    return response.data;
  },

  // Get user profile
  async getUserProfile(): Promise<{ uid: string; email?: string; email_verified: boolean }> {
    const response = await api.get('/api/user/profile');
    return response.data;
  },

  // Get transactions
  async getTransactions(): Promise<TransactionResponse[]> {
    const response = await api.get<TransactionResponse[]>('/api/transactions');
    return response.data;
  },

  // Get single transaction
  async getTransaction(transactionId: string): Promise<TransactionResponse> {
    const response = await api.get<TransactionResponse>(`/api/transactions/${transactionId}`);
    return response.data;
  },

  // Get SHAP explanation for transaction (longer timeout for SHAP calculations)
  async getTransactionExplanation(transactionId: string): Promise<SHAPExplanationResponse> {
    const response = await api.get<SHAPExplanationResponse>(`/api/transactions/${transactionId}/explain`, {
      timeout: 90000 // 90 seconds for SHAP explanations
    });
    return response.data;
  },

  // Flag or unflag a transaction
  async flagTransaction(transactionId: string, request: FlagTransactionRequest): Promise<FlagTransactionResponse> {
    const response = await api.post<FlagTransactionResponse>(`/api/transactions/${transactionId}/flag`, request);
    return response.data;
  }
};

export default api;

