"""
Synthetic Transaction Data Generator for FraudDetectPro
Generates realistic transaction data and sends to API every minute
"""

import numpy as np
import pandas as pd
import requests
import time
import logging
from datetime import datetime
from typing import Dict, List
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
API_URL = os.getenv('FASTAPI_URL', 'http://localhost:8000')
GENERATION_INTERVAL = 60  # seconds (1 minute)
BATCH_SIZE = 20  # Generate 10 transactions per batch
FRAUD_RATIO = 0.05  # 5% fraud rate (can be adjusted via --fraud-ratio argument)

# Setup logging with UTF-8 support for Windows console
import sys
import io

# Create a StreamHandler that handles encoding errors gracefully
class SafeStreamHandler(logging.StreamHandler):
    """StreamHandler that handles Unicode encoding errors gracefully"""
    def emit(self, record):
        try:
            super().emit(record)
        except UnicodeEncodeError:
            # If encoding fails, replace problematic characters
            try:
                msg = self.format(record)
                # Replace common emojis with ASCII equivalents
                msg = msg.replace('✅', '[OK]').replace('❌', '[X]')
                msg = msg.replace('🔍', '[?]').replace('⚠️', '[!]')
                stream = self.stream
                stream.write(msg + self.terminator)
                self.flush()
            except Exception:
                self.handleError(record)

# Create handlers
file_handler = logging.FileHandler('synthetic_generator.log', encoding='utf-8')
stream_handler = SafeStreamHandler(sys.stdout)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[file_handler, stream_handler]
)
logger = logging.getLogger(__name__)


class SyntheticTransactionGenerator:
    """Generate realistic synthetic credit card transactions"""
    
    def __init__(self, fraud_ratio: float = 0.05, ambiguous_ratio: float = 0.15):
        self.fraud_ratio = fraud_ratio
        self.ambiguous_ratio = ambiguous_ratio  # Transactions requiring review
        self.transaction_count = 0
        self.fraud_count = 0
        self.ambiguous_count = 0
        
        # Statistical parameters from real credit card data
        self.legitimate_params = {
            'time_mean': 94813.86,
            'time_std': 47488.15,
            'amount_mean': 88.35,
            'amount_std': 250.12,
            'v_means': np.zeros(28),  # PCA features centered around 0
            'v_stds': np.ones(28) * 1.96  # Standard deviation for PCA features
        }
        
        self.fraud_params = {
            'time_mean': 80746.81,
            'time_std': 47835.45,
            'amount_mean': 122.21,
            'amount_std': 256.68,
            'v_means': np.zeros(28),
            'v_stds': np.ones(28) * 3.5  # Larger variance for fraud
        }
        
        logger.info("Synthetic Transaction Generator initialized")
        logger.info(f"Fraud ratio: {fraud_ratio * 100}%")
        logger.info(f"Ambiguous/Review ratio: {ambiguous_ratio * 100}%")
    
    def generate_legitimate_transaction(self) -> Dict:
        """Generate a legitimate transaction"""
        # Time (seconds from first transaction)
        time_val = max(0, np.random.normal(
            self.legitimate_params['time_mean'],
            self.legitimate_params['time_std']
        ))
        
        # Amount (typical legitimate range: $1-$500)
        amount = max(1.0, np.random.lognormal(
            np.log(self.legitimate_params['amount_mean']),
            0.8
        ))
        amount = min(amount, 500.0)  # Cap at reasonable amount
        
        # V1-V28 (PCA features)
        v_features = np.random.normal(
            self.legitimate_params['v_means'],
            self.legitimate_params['v_stds']
        )
        
        # Ensure v_features is a numpy array before clipping
        if not isinstance(v_features, np.ndarray):
            v_features = np.array(v_features, dtype=float)
        
        # Ensure features are within reasonable bounds
        v_features = np.clip(v_features, -5, 5).tolist()
        
        # Combine all features: [Time, V1-V28, Amount]
        features = [float(time_val)] + [float(v) for v in v_features] + [float(amount)]
        
        return {
            'features': features,
            'true_label': 'Legitimate',
            'amount': amount,
            'time': time_val
        }
    
    def generate_fraud_transaction(self) -> Dict:
        """Generate a realistic fraudulent transaction by sampling from real frauds and adding noise."""
        # Load real frauds from dataset
        data_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'raw', 'creditcard.csv')
        
        try:
            df = pd.read_csv(data_path)
            fraud_df = df[df['Class'] == 1]
            
            if len(fraud_df) == 0:
                # Fallback: Generate synthetic fraud if no real frauds available
                logger.warning("No fraud data found in dataset, generating synthetic fraud...")
                return self._generate_synthetic_fraud()
            
            row = fraud_df.sample(1).iloc[0]
            
            # Extract Time feature (first feature expected by model)
            time_val = float(row['Time'])
            
            # Extract V1-V28 features and add slight noise for variety
            v_features = [float(row[f'V{i}']) + np.random.normal(0, 0.1) for i in range(1, 29)]
            
            # Extract Amount and add slight noise
            amount = float(row['Amount']) + np.random.normal(0, 2.0)
            amount = max(1.0, min(amount, 2500.0))  # Clip to reasonable range
            
            # Ensure v_features is a numpy array before clipping
            if not isinstance(v_features, np.ndarray):
                v_features = np.array(v_features, dtype=float)
            
            # Clip V features to reasonable range (based on PCA feature ranges)
            v_features = np.clip(v_features, -10, 10).tolist()
            
            # Combine features in correct order: [Time, V1-V28, Amount] = 30 features
            features = [float(time_val)] + [float(v) for v in v_features] + [float(amount)]
            
            if len(features) != 30:
                logger.error(f"Feature count mismatch! Expected 30, got {len(features)}")
                return self._generate_synthetic_fraud()
            
            return {
                'features': features,
                'true_label': 'Fraudulent',
                'amount': amount,
                'time': time_val
            }
        except Exception as e:
            logger.error(f"Error generating fraud transaction from real data: {e}")
            logger.info("Falling back to synthetic fraud generation...")
            return self._generate_synthetic_fraud()
    
    def _generate_synthetic_fraud(self) -> Dict:
        """Generate synthetic fraudulent transaction with fraud-like characteristics."""
        # Load real fraud data to get realistic patterns
        try:
            data_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'raw', 'creditcard.csv')
            df = pd.read_csv(data_path)
            fraud_df = df[df['Class'] == 1]
            
            if len(fraud_df) > 0:
                # Sample a real fraud transaction as base
                base_row = fraud_df.sample(1).iloc[0]
                time_val = float(base_row['Time'])
                amount = float(base_row['Amount'])
                
                # Modify V features to be more extreme (fraud indicators)
                v_features = []
                for i in range(1, 29):
                    base_val = float(base_row[f'V{i}'])
                    # Add more variance and make some values extreme
                    if np.random.random() < 0.4:  # 40% chance of extreme value
                        v_feature = base_val * (1 + np.random.normal(0, 0.5))
                        # Make it more extreme
                        if abs(v_feature) < 2:
                            v_feature = v_feature * (2 + np.random.random() * 2)
                    else:
                        v_feature = base_val + np.random.normal(0, 0.3)
                    
                    v_features.append(v_feature)
                
                # Make amount potentially higher (fraud often involves larger amounts)
                amount = amount * (1 + np.random.uniform(0, 0.5))
                amount = max(1.0, min(amount, 2500.0))
                
            else:
                # Fallback if no fraud data available
                time_val = max(0, np.random.normal(self.fraud_params['time_mean'], self.fraud_params['time_std']))
                amount = max(1.0, np.random.lognormal(np.log(self.fraud_params['amount_mean']), 1.2))
                amount = min(amount, 2500.0)
                
                v_features = []
                for i in range(28):
                    # Generate more extreme values for fraud
                    if np.random.random() < 0.5:  # 50% chance of outlier
                        v_feature = np.random.normal(0, 4.0)  # Extreme value
                    else:
                        v_feature = np.random.normal(self.fraud_params['v_means'][i], self.fraud_params['v_stds'][i] * 1.5)
                    v_features.append(v_feature)
        
        except Exception as e:
            logger.warning(f"Could not load fraud data for synthetic generation: {e}")
            # Pure synthetic fallback
            time_val = max(0, np.random.normal(self.fraud_params['time_mean'], self.fraud_params['time_std']))
            amount = max(1.0, np.random.lognormal(np.log(self.fraud_params['amount_mean']), 1.2))
            amount = min(amount, 2500.0)
            
            v_features = []
            for i in range(28):
                v_feature = np.random.normal(0, 4.0) if np.random.random() < 0.5 else np.random.normal(0, 3.0)
                v_features.append(v_feature)
        
        # Ensure v_features is a list with exactly 28 elements
        if not isinstance(v_features, list):
            v_features = list(v_features)
        
        if len(v_features) != 28:
            logger.error(f"v_features has wrong length in synthetic fraud: {len(v_features)}, expected 28")
            v_features = [float(np.random.normal(0, 3.0)) for _ in range(28)]
        
        # Clip to reasonable bounds (but allow more extreme values for fraud)
        v_features = np.clip(np.array(v_features, dtype=float), -12, 12).tolist()
        
        # Combine: [Time, V1-V28, Amount]
        features = [float(time_val)] + [float(v) for v in v_features] + [float(amount)]
        
        # Validate feature count
        if len(features) != 30:
            logger.error(f"Features have wrong count in synthetic fraud: {len(features)}, expected 30")
            raise ValueError(f"Feature count mismatch: got {len(features)}, expected 30")
        
        logger.debug(f"Generated synthetic fraud: amount={amount:.2f}, time={time_val:.1f}, V1={v_features[0]:.3f}")
        
        return {
            'features': features,
            'true_label': 'Fraudulent',
            'amount': amount,
            'time': time_val
        }
    
    def generate_ambiguous_transaction(self) -> Dict:
        """Generate an ambiguous transaction that requires analyst review.
        These have characteristics between legitimate and fraud."""
        # Try to base on real data for realism
        try:
            data_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'raw', 'creditcard.csv')
            df = pd.read_csv(data_path)
            
            # Mix legitimate and fraud to create ambiguity
            use_fraud_base = np.random.random() < 0.5
            
            if use_fraud_base:
                fraud_df = df[df['Class'] == 1]
                if len(fraud_df) > 0:
                    base_row = fraud_df.sample(1).iloc[0]
                    # Make it less extreme (move toward legitimate)
                    time_val = float(base_row['Time']) + np.random.normal(0, 10000)
                    amount = float(base_row['Amount']) * np.random.uniform(0.7, 1.2)
                    
                    # Make V features more moderate (between fraud and legitimate)
                    v_features = []
                    for i in range(1, 29):
                        base_val = float(base_row[f'V{i}'])
                        # Reduce extremes - bring closer to 0 but keep some pattern
                        v_feature = base_val * np.random.uniform(0.5, 0.8) + np.random.normal(0, 1.0)
                        v_features.append(v_feature)
                    
                    # Amount in moderate range
                    amount = max(50.0, min(amount, 800.0))
                else:
                    # Fallback
                    time_val = max(0, np.random.normal(90000, 30000))
                    amount = np.random.uniform(100, 500)
                    v_features = [np.random.normal(0, 2.0) for _ in range(28)]
            else:
                # Start with legitimate, add some suspicious elements
                legit_df = df[df['Class'] == 0]
                if len(legit_df) > 0:
                    base_row = legit_df.sample(1).iloc[0]
                    time_val = float(base_row['Time'])
                    
                    # Make amount slightly higher (suspicious)
                    amount = float(base_row['Amount']) * np.random.uniform(1.5, 3.0)
                    amount = max(100.0, min(amount, 1000.0))
                    
                    # Make some V features more extreme (suspicious patterns)
                    v_features = []
                    for i in range(1, 29):
                        base_val = float(base_row[f'V{i}'])
                        # Add some suspicious patterns to some features
                        if np.random.random() < 0.3:  # 30% of features become suspicious
                            v_feature = base_val * np.random.uniform(1.5, 2.5) + np.random.normal(0, 1.5)
                        else:
                            v_feature = base_val + np.random.normal(0, 0.5)
                        v_features.append(v_feature)
                else:
                    # Fallback
                    time_val = max(0, np.random.normal(90000, 30000))
                    amount = np.random.uniform(150, 600)
                    v_features = [np.random.normal(0, 2.5) for _ in range(28)]
                    
        except Exception as e:
            logger.warning(f"Error loading data for ambiguous transaction: {e}")
            # Pure synthetic ambiguous transaction
            time_val = max(0, np.random.normal(
                (self.legitimate_params['time_mean'] + self.fraud_params['time_mean']) / 2,
                (self.legitimate_params['time_std'] + self.fraud_params['time_std']) / 2
            ))
            
            # Amount in moderate-high range (suspicious but not extreme)
            amount = max(100.0, np.random.lognormal(
                np.log((self.legitimate_params['amount_mean'] + self.fraud_params['amount_mean']) / 2),
                0.9
            ))
            amount = min(amount, 800.0)
            
            # V features: mix of moderate and slightly extreme
            v_features = []
            for i in range(28):
                if np.random.random() < 0.25:  # 25% chance of suspicious feature
                    v_feature = np.random.normal(0, 2.5)  # Slightly extreme
                else:
                    v_feature = np.random.normal(0, 1.8)  # Moderate
                v_features.append(v_feature)
        
        # Ensure v_features is a list and has exactly 28 elements
        if not isinstance(v_features, list):
            v_features = list(v_features)
        
        if len(v_features) != 28:
            logger.error(f"v_features has wrong length: {len(v_features)}, expected 28")
            # Regenerate if wrong length
            v_features = [float(np.random.normal(0, 2.0)) for _ in range(28)]
        
        # Clip to reasonable bounds (wider than legitimate but narrower than fraud)
        v_features = np.clip(np.array(v_features, dtype=float), -8, 8).tolist()
        
        # Combine: [Time, V1-V28, Amount]
        features = [float(time_val)] + [float(v) for v in v_features] + [float(amount)]
        
        # Validate feature count
        if len(features) != 30:
            logger.error(f"Features have wrong count: {len(features)}, expected 30")
            raise ValueError(f"Feature count mismatch: got {len(features)}, expected 30")
        
        logger.debug(f"Generated ambiguous transaction: amount={amount:.2f}, time={time_val:.1f}")
        
        return {
            'features': features,
            'true_label': 'Ambiguous',  # Will need review
            'amount': amount,
            'time': time_val
        }
    
    def generate_batch(self, batch_size: int = 10) -> List[Dict]:
        """Generate a batch of transactions including fraud, legitimate, and ambiguous (review) transactions.
        Distribution is randomized while maintaining target ratios on average."""
        transactions = []
        
        # Randomize the distribution while maintaining target ratios
        # Use multinomial distribution to randomly assign transaction types
        remaining_slots = batch_size
        n_fraud = 0
        n_ambiguous = 0
        n_legitimate = 0
        
        # Ensure we always have at least 1 fraud and 1 ambiguous for variety
        min_fraud = 1 if batch_size >= 3 else (1 if batch_size >= 1 else 0)
        min_ambiguous = 1 if batch_size >= 3 else (0 if batch_size <= 1 else (1 if np.random.random() < 0.5 else 0))
        
        # Calculate remaining slots after minimums
        remaining_slots = batch_size - min_fraud - min_ambiguous
        
        if remaining_slots > 0:
            # Randomly distribute remaining slots based on target ratios
            # Create probability distribution (normalized so they sum to 1)
            total_target_ratio = self.fraud_ratio + self.ambiguous_ratio
            if total_target_ratio >= 1.0:
                # Adjust if ratios exceed 100%
                self.fraud_ratio = min(self.fraud_ratio, 0.4)
                self.ambiguous_ratio = min(self.ambiguous_ratio, 0.3)
                total_target_ratio = self.fraud_ratio + self.ambiguous_ratio
            
            legitimate_ratio = max(0.1, 1.0 - total_target_ratio)
            
            # Add some randomness to the distribution (±20% of target ratio)
            fraud_ratio_randomized = max(0.0, self.fraud_ratio + np.random.normal(0, self.fraud_ratio * 0.2))
            ambiguous_ratio_randomized = max(0.0, self.ambiguous_ratio + np.random.normal(0, self.ambiguous_ratio * 0.2))
            legitimate_ratio_randomized = max(0.1, 1.0 - fraud_ratio_randomized - ambiguous_ratio_randomized)
            
            # Normalize
            total_randomized = fraud_ratio_randomized + ambiguous_ratio_randomized + legitimate_ratio_randomized
            fraud_ratio_randomized /= total_randomized
            ambiguous_ratio_randomized /= total_randomized
            legitimate_ratio_randomized /= total_randomized
            
            # Use multinomial to randomly assign remaining slots
            # This gives natural variation while maintaining average ratios
            probabilities = [fraud_ratio_randomized, ambiguous_ratio_randomized, legitimate_ratio_randomized]
            random_counts = np.random.multinomial(remaining_slots, probabilities)
            
            n_fraud = min_fraud + int(random_counts[0])
            n_ambiguous = min_ambiguous + int(random_counts[1])
            n_legitimate = int(random_counts[2])
        else:
            # Very small batch - use minimums only
            n_fraud = min_fraud
            n_ambiguous = min_ambiguous
            n_legitimate = 0
        
        # Ensure we don't exceed batch size (shouldn't happen, but safety check)
        total = n_fraud + n_ambiguous + n_legitimate
        if total > batch_size:
            # Trim from legitimate first
            excess = total - batch_size
            n_legitimate = max(0, n_legitimate - excess)
        elif total < batch_size:
            # Add to legitimate
            n_legitimate += (batch_size - total)
        
        # Generate fraud transactions
        for _ in range(n_fraud):
            transaction = self.generate_fraud_transaction()
            self.transaction_count += 1
            self.fraud_count += 1
            transaction['transaction_id'] = f"SYNTH_{self.transaction_count:06d}"
            transaction['timestamp'] = datetime.now().isoformat()
            transactions.append(transaction)
            logger.debug(f"Generated fraud transaction: {transaction['transaction_id']}")
        
        # Generate ambiguous/review transactions
        for _ in range(n_ambiguous):
            transaction = self.generate_ambiguous_transaction()
            self.transaction_count += 1
            self.ambiguous_count += 1
            transaction['transaction_id'] = f"SYNTH_{self.transaction_count:06d}"
            transaction['timestamp'] = datetime.now().isoformat()
            transactions.append(transaction)
            logger.debug(f"Generated ambiguous transaction: {transaction['transaction_id']}")
        
        # Generate legitimate transactions
        for _ in range(n_legitimate):
            transaction = self.generate_legitimate_transaction()
            self.transaction_count += 1
            transaction['transaction_id'] = f"SYNTH_{self.transaction_count:06d}"
            transaction['timestamp'] = datetime.now().isoformat()
            transactions.append(transaction)
        
        # Shuffle to mix transaction types
        np.random.shuffle(transactions)
        
        # Calculate actual ratios for this batch
        actual_fraud_ratio = (n_fraud / batch_size * 100) if batch_size > 0 else 0
        actual_ambiguous_ratio = (n_ambiguous / batch_size * 100) if batch_size > 0 else 0
        actual_legitimate_ratio = (n_legitimate / batch_size * 100) if batch_size > 0 else 0
        
        logger.info(
            f"Generated batch (randomized): {n_fraud} fraud ({actual_fraud_ratio:.1f}%), "
            f"{n_ambiguous} ambiguous/review ({actual_ambiguous_ratio:.1f}%), "
            f"{n_legitimate} legitimate ({actual_legitimate_ratio:.1f}%)"
        )
        return transactions
    
    def get_statistics(self) -> Dict:
        """Get generator statistics"""
        legitimate_generated = self.transaction_count - self.fraud_count - self.ambiguous_count
        return {
            'total_generated': self.transaction_count,
            'fraud_generated': self.fraud_count,
            'ambiguous_generated': self.ambiguous_count,
            'legitimate_generated': legitimate_generated,
            'actual_fraud_ratio': (self.fraud_count / self.transaction_count * 100) if self.transaction_count > 0 else 0,
            'actual_ambiguous_ratio': (self.ambiguous_count / self.transaction_count * 100) if self.transaction_count > 0 else 0
        }


class TransactionSender:
    """Send transactions to the API"""
    
    def __init__(self, api_url: str):
        self.api_url = api_url
        self.successful_predictions = 0
        self.failed_predictions = 0
        self.results_log = []
        
        logger.info(f"Transaction Sender initialized for API: {api_url}")
    
    def check_api_health(self) -> bool:
        """Check if API is available"""
        try:
            response = requests.get(f"{self.api_url}/health", timeout=5)
            if response.status_code == 200:
                logger.info("API health check passed")
                return True
            else:
                logger.warning(f"API health check failed: status {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"API health check failed: {e}")
            return False
    
    def send_transaction(self, transaction: Dict) -> Dict:
        """Send a single transaction to the API"""
        try:
            # Prepare payload
            payload = {
                "features": transaction['features']
            }
            
            # Send request
            response = requests.post(
                f"{self.api_url}/predict",
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                try:
                    result = response.json()
                except ValueError as json_err:
                    # Response is not valid JSON
                    logger.error(f"API returned non-JSON response (status {response.status_code}): {response.text[:200]}")
                    self.failed_predictions += 1
                    return None
                
                self.successful_predictions += 1
                
                # Check if prediction matches true label
                predicted_label = result['prediction']
                true_label = transaction['true_label']
                probability = result['probability']
                
                # For ambiguous transactions, check if they're flagged for review
                # Probability is now in percentage (0-100) from API
                if true_label == 'Ambiguous':
                    # Ambiguous transactions are "correct" if they get medium risk (review status)
                    # Probability between 30% and 70% is ideal for review
                    is_correct = 30 <= probability <= 70
                    status_note = " (Review)" if is_correct else " (Not in review range)"
                else:
                    is_correct = predicted_label == true_label
                    status_note = ""
                
                log_entry = {
                    'transaction_id': transaction['transaction_id'],
                    'timestamp': transaction['timestamp'],
                    'true_label': true_label,
                    'predicted_label': predicted_label,
                    'probability': probability,
                    'amount': transaction['amount'],
                    'is_correct': is_correct
                }
                
                self.results_log.append(log_entry)
                
                # Log result with special handling for ambiguous
                if true_label == 'Ambiguous':
                    emoji = "🔍" if is_correct else "⚠️"
                else:
                    emoji = "✅" if is_correct else "❌"
                    
                logger.info(
                    f"{emoji} {transaction['transaction_id']} | "
                    f"True: {true_label} | Pred: {predicted_label} | "
                    f"Prob: {probability:.2f}%{status_note} | "
                    f"Amount: ${transaction['amount']:.2f}"
                )
                
                return log_entry
            else:
                self.failed_predictions += 1
                try:
                    error_detail = response.json().get('detail', response.text[:200])
                except ValueError:
                    error_detail = f"HTTP {response.status_code}: {response.text[:200]}"
                logger.error(f"Prediction failed (status {response.status_code}): {error_detail}")
                return None
                
        except requests.exceptions.Timeout:
            self.failed_predictions += 1
            logger.error(f"Request timeout: API did not respond within 10 seconds")
            return None
        except requests.exceptions.ConnectionError:
            self.failed_predictions += 1
            logger.error(f"Connection error: API server may not be running")
            return None
        except Exception as e:
            self.failed_predictions += 1
            logger.error(f"Error sending transaction: {type(e).__name__}: {e}")
            return None
    
    def send_batch(self, transactions: List[Dict]) -> List[Dict]:
        """Send a batch of transactions"""
        results = []
        
        logger.info(f"Sending batch of {len(transactions)} transactions...")
        
        for transaction in transactions:
            result = self.send_transaction(transaction)
            if result:
                results.append(result)
            time.sleep(0.1)  # Small delay between requests
        
        return results
    
    def get_statistics(self) -> Dict:
        """Get sender statistics"""
        total_sent = self.successful_predictions + self.failed_predictions
        
        if len(self.results_log) > 0:
            correct_predictions = sum(1 for r in self.results_log if r['is_correct'])
            accuracy = (correct_predictions / len(self.results_log)) * 100
        else:
            accuracy = 0
        
        return {
            'total_sent': total_sent,
            'successful': self.successful_predictions,
            'failed': self.failed_predictions,
            'accuracy': accuracy
        }
    
    def save_results(self, filename: str = 'synthetic_results.json'):
        """Save results to file"""
        with open(filename, 'w') as f:
            json.dump(self.results_log, f, indent=2)
        logger.info(f"Results saved to {filename}")


class SyntheticDataPipeline:
    """Main pipeline to generate and send synthetic data"""
    
    def __init__(self, api_url: str, interval: int = 60, batch_size: int = 10, fraud_ratio: float = 0.05, ambiguous_ratio: float = 0.15):
        self.generator = SyntheticTransactionGenerator(fraud_ratio, ambiguous_ratio)
        self.sender = TransactionSender(api_url)
        self.interval = interval
        self.batch_size = batch_size
        self.is_running = False
        
        logger.info("=" * 60)
        logger.info("Synthetic Data Pipeline Initialized")
        logger.info(f"API URL: {api_url}")
        logger.info(f"Interval: {interval} seconds")
        logger.info(f"Batch size: {batch_size} transactions")
        logger.info(f"Target fraud ratio: {fraud_ratio * 100}%")
        logger.info(f"Target ambiguous/review ratio: {ambiguous_ratio * 100}%")
        logger.info("=" * 60)
    
    def run_once(self):
        """Run one cycle of generation and sending"""
        logger.info(f"\n{'='*60}")
        logger.info(f"Starting generation cycle at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"{'='*60}")
        
        # Generate transactions
        transactions = self.generator.generate_batch(self.batch_size)
        logger.info(f"Generated {len(transactions)} transactions")
        
        # Send to API
        results = self.sender.send_batch(transactions)
        
        # Print statistics
        gen_stats = self.generator.get_statistics()
        send_stats = self.sender.get_statistics()
        
        logger.info(f"\nGeneration Statistics:")
        logger.info(f"   Total generated: {gen_stats['total_generated']}")
        logger.info(f"   Fraud: {gen_stats['fraud_generated']} ({gen_stats['actual_fraud_ratio']:.2f}%)")
        logger.info(f"   Ambiguous/Review: {gen_stats['ambiguous_generated']} ({gen_stats['actual_ambiguous_ratio']:.2f}%)")
        logger.info(f"   Legitimate: {gen_stats['legitimate_generated']}")
        
        logger.info(f"\nPrediction Statistics:")
        logger.info(f"   Total sent: {send_stats['total_sent']}")
        logger.info(f"   Successful: {send_stats['successful']}")
        logger.info(f"   Failed: {send_stats['failed']}")
        logger.info(f"   Accuracy: {send_stats['accuracy']:.2f}%")
        
        return results
    
    def run_continuous(self):
        """Run continuously with specified interval"""
        self.is_running = True
        
        # Check API health first
        if not self.sender.check_api_health():
            logger.error("API is not available. Please start the API first.")
            return
        
        logger.info("Starting continuous generation...")
        logger.info(f"Will generate every {self.interval} seconds")
        logger.info("Press Ctrl+C to stop\n")
        
        cycle_count = 0
        
        try:
            while self.is_running:
                cycle_count += 1
                logger.info(f"\nCycle #{cycle_count}")
            
                self.run_once()
                
                # Wait for next cycle
                logger.info(f"\n Waiting {self.interval} seconds until next cycle...")
                time.sleep(self.interval)
                
        except KeyboardInterrupt:
            logger.info("\n\nStopping synthetic data generation...")
            self.stop()
        except Exception as e:
            logger.error(f" Error in continuous run: {e}")
            self.stop()
    
    def stop(self):
        """Stop the pipeline and save results"""
        self.is_running = False
        
        # Save results
        self.sender.save_results()
        
        # Final statistics
        gen_stats = self.generator.get_statistics()
        send_stats = self.sender.get_statistics()
        
        logger.info("\n" + "=" * 60)
        logger.info("FINAL STATISTICS")
        logger.info("=" * 60)
        logger.info(f"\nGeneration:")
        logger.info(f"  Total transactions: {gen_stats['total_generated']}")
        logger.info(f"  Fraud: {gen_stats['fraud_generated']} ({gen_stats['actual_fraud_ratio']:.2f}%)")
        logger.info(f"  Ambiguous/Review: {gen_stats['ambiguous_generated']} ({gen_stats['actual_ambiguous_ratio']:.2f}%)")
        logger.info(f"  Legitimate: {gen_stats['legitimate_generated']}")
        
        logger.info(f"\nPrediction:")
        logger.info(f"  Total sent: {send_stats['total_sent']}")
        logger.info(f"  Successful: {send_stats['successful']}")
        logger.info(f"  Failed: {send_stats['failed']}")
        logger.info(f"  Model Accuracy: {send_stats['accuracy']:.2f}%")
        
        logger.info("\nPipeline stopped successfully")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Synthetic Transaction Generator for FraudDetectPro')
    parser.add_argument('--api-url', default='http://localhost:8000', help='FastAPI URL')
    parser.add_argument('--interval', type=int, default=60, help='Generation interval in seconds')
    parser.add_argument('--batch-size', type=int, default=10, help='Transactions per batch')
    parser.add_argument('--fraud-ratio', type=float, default=0.05, help='Fraud ratio (0.0-1.0)')
    parser.add_argument('--ambiguous-ratio', type=float, default=0.15, help='Ambiguous/Review ratio (0.0-1.0)')
    parser.add_argument('--once', action='store_true', help='Run once and exit')
    
    args = parser.parse_args()
    
    # Create pipeline
    pipeline = SyntheticDataPipeline(
        api_url=args.api_url,
        interval=args.interval,
        batch_size=args.batch_size,
        fraud_ratio=args.fraud_ratio,
        ambiguous_ratio=args.ambiguous_ratio
    )
    
    if args.once:
        # Run once
        pipeline.run_once()
    else:
        # Run continuously
        pipeline.run_continuous()


if __name__ == "__main__":
    main()