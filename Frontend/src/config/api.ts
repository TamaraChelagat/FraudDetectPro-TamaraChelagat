// API Configuration
// @ts-ignore - Vite env variables
const API_BASE_URL = (import.meta.env?.VITE_API_URL as string) || 'http://localhost:8000';

export const API_CONFIG = {
  baseURL: API_BASE_URL,
  timeout: 60000, // Increased to 60 seconds for SHAP explanations
  headers: {
    'Content-Type': 'application/json',
  }
};

export default API_CONFIG;

