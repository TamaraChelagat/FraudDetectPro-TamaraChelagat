import { Header } from "@/components/layout/Header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Progress } from "@/components/ui/progress";
import { AlertTriangle, CheckCircle, Loader2, Upload, FileText, Download, Clipboard } from "lucide-react";
import { useState, useEffect, useRef } from "react";
import { apiService, PredictionResponse } from "@/services/api";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";

interface BatchPredictionResult {
  transactionId: number;
  prediction: string;
  probability: number;
  status: 'success' | 'error';
  errorMessage?: string;
  transaction_id?: string;  // Real transaction ID from API for SHAP explanation
}

export default function ManualPrediction() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{
    prediction: string;
    probability: number;
    threshold_used: number;
    transaction_id?: string;
  } | null>(null);
  
  // CSV Upload state
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvData, setCsvData] = useState<number[][]>([]);
  const [csvParsing, setCsvParsing] = useState(false);
  const [batchLoading, setBatchLoading] = useState(false);
  const [batchProgress, setBatchProgress] = useState(0);
  const [batchResults, setBatchResults] = useState<BatchPredictionResult[]>([]);
  const [showBatchResults, setShowBatchResults] = useState(false);
  
  // Paste center state - single transaction features (must be declared before useEffect)
  const [pastedFeatures, setPastedFeatures] = useState("");
  const [parseError, setParseError] = useState<string | null>(null);
  
  // Track if this is the initial mount to prevent saving on restore
  const isInitialMount = useRef(true);
  
  // Restore batch results and paste center results from sessionStorage on mount
  useEffect(() => {
    const savedResults = sessionStorage.getItem('manualPrediction_batchResults');
    const savedCsvData = sessionStorage.getItem('manualPrediction_csvData');
    const savedShowResults = sessionStorage.getItem('manualPrediction_showResults');
    const savedPasteResult = sessionStorage.getItem('manualPrediction_pasteResult');
    const savedPastedFeatures = sessionStorage.getItem('manualPrediction_pastedFeatures');
    
    if (savedResults) {
      try {
        setBatchResults(JSON.parse(savedResults));
      } catch (e) {
        console.error('Failed to restore batch results:', e);
      }
    }
    
    if (savedCsvData) {
      try {
        setCsvData(JSON.parse(savedCsvData));
      } catch (e) {
        console.error('Failed to restore CSV data:', e);
      }
    }
    
    if (savedShowResults === 'true') {
      setShowBatchResults(true);
    }
    
    if (savedPasteResult) {
      try {
        setResult(JSON.parse(savedPasteResult));
      } catch (e) {
        console.error('Failed to restore paste result:', e);
      }
    }
    
    if (savedPastedFeatures) {
      try {
        setPastedFeatures(savedPastedFeatures);
      } catch (e) {
        console.error('Failed to restore pasted features:', e);
      }
    }
    
    // Mark initial mount as complete
    isInitialMount.current = false;
  }, []);
  
  // Save batch results to sessionStorage whenever they change
  useEffect(() => {
    // Skip saving on initial mount (when restoring from sessionStorage)
    if (isInitialMount.current) return;
    
    if (batchResults.length > 0) {
      sessionStorage.setItem('manualPrediction_batchResults', JSON.stringify(batchResults));
    }
  }, [batchResults]);
  
  // Save CSV data to sessionStorage whenever it changes
  useEffect(() => {
    // Skip saving on initial mount (when restoring from sessionStorage)
    if (isInitialMount.current) return;
    
    if (csvData.length > 0) {
      sessionStorage.setItem('manualPrediction_csvData', JSON.stringify(csvData));
    }
  }, [csvData]);
  
  // Save showBatchResults state
  useEffect(() => {
    // Skip saving on initial mount (when restoring from sessionStorage)
    if (isInitialMount.current) return;
    
    sessionStorage.setItem('manualPrediction_showResults', showBatchResults.toString());
  }, [showBatchResults]);
  
  // Save paste center result to sessionStorage whenever it changes
  useEffect(() => {
    // Skip saving on initial mount (when restoring from sessionStorage)
    if (isInitialMount.current) return;
    
    if (result) {
      sessionStorage.setItem('manualPrediction_pasteResult', JSON.stringify(result));
    }
  }, [result]);
  
  // Save pastedFeatures to sessionStorage whenever it changes
  useEffect(() => {
    // Skip saving on initial mount (when restoring from sessionStorage)
    if (isInitialMount.current) return;
    
    if (pastedFeatures) {
      sessionStorage.setItem('manualPrediction_pastedFeatures', pastedFeatures);
    }
  }, [pastedFeatures]);

  // CSV File Handling
  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    // Validate file type
    const fileExtension = file.name.split('.').pop()?.toLowerCase();
    if (fileExtension !== 'csv') {
      toast.error("Invalid file format! Please upload a CSV file (.csv extension only).");
      setCsvFile(null);
      setCsvData([]);
      return;
    }

    setCsvFile(file);
    setCsvData([]);
    setBatchResults([]);
    setShowBatchResults(false);
    setCsvParsing(true);

    // Read and parse CSV
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const text = e.target?.result as string;
        if (!text || text.trim().length === 0) {
          toast.error("CSV file is empty.");
          setCsvFile(null);
          setCsvData([]);
          return;
        }

        // Handle different line endings (Windows \r\n, Unix \n, Mac \r)
        const lines = text.split(/\r?\n|\r/).filter(line => line.trim().length > 0);
        
        if (lines.length === 0) {
          toast.error("No data found in CSV file.");
          setCsvFile(null);
          setCsvData([]);
          return;
        }

        console.log(`CSV file has ${lines.length} lines`);
        
        // Parse CSV (improved parser)
        const parsedData: number[][] = [];
        let headerSkipped = false;
        
        for (let i = 0; i < lines.length; i++) {
          const line = lines[i].trim();
          if (!line) continue;
          
          // Try to detect delimiter (comma, semicolon, or tab)
          let delimiter = ',';
          if (line.includes(';') && line.split(';').length > line.split(',').length) {
            delimiter = ';';
          } else if (line.includes('\t') && line.split('\t').length > line.split(',').length) {
            delimiter = '\t';
          }
          
          // Parse CSV line (handle quoted values)
          const values: string[] = [];
          let currentValue = '';
          let inQuotes = false;
          
          for (let j = 0; j < line.length; j++) {
            const char = line[j];
            if (char === '"') {
              inQuotes = !inQuotes;
            } else if (char === delimiter && !inQuotes) {
              values.push(currentValue.trim());
              currentValue = '';
            } else {
              currentValue += char;
            }
          }
          values.push(currentValue.trim()); // Add last value
          
          // Convert to numbers
          const numericValues = values.map(v => {
            const cleaned = v.replace(/^"|"$/g, '').trim();
            const num = parseFloat(cleaned);
            return isNaN(num) ? 0 : num;
          });
          
          // Check if first row is a header (contains non-numeric values or has wrong column count)
          if (i === 0 && !headerSkipped) {
            const hasNonNumeric = values.some(v => {
              const cleaned = v.replace(/^"|"$/g, '').trim();
              return isNaN(parseFloat(cleaned)) && cleaned.length > 0;
            });
            
            if (hasNonNumeric || numericValues.length !== 30) {
              console.log(`Skipping header row (row 1): ${numericValues.length} columns, hasNonNumeric: ${hasNonNumeric}`);
              headerSkipped = true;
              continue;
            }
          }
          
          // Accept 30 columns (features only) or 31 columns (features + class label)
          if (numericValues.length === 30) {
            parsedData.push(numericValues);
          } else if (numericValues.length === 31) {
            // If 31 columns, drop the last one (Class label) and use first 30
            parsedData.push(numericValues.slice(0, 30));
            console.log(`Row ${i + 1}: Dropped Class column (31 columns -> 30 features)`);
          } else {
            console.warn(`Row ${i + 1} has ${numericValues.length} columns, expected 30 or 31. Values: ${values.slice(0, 5).join(', ')}...`);
            toast.warning(`Row ${i + 1} has ${numericValues.length} columns, expected 30 or 31. Skipping.`);
          }
        }
        
        console.log(`Parsed ${parsedData.length} valid transactions from ${lines.length} total lines`);
        
        if (parsedData.length === 0) {
          toast.error(
            `No valid transaction data found in CSV. ` +
            `Expected 30 numeric columns per row. ` +
            `Found ${lines.length} line(s). ` +
            `Please check your CSV format.`
          );
          setCsvFile(null);
          setCsvData([]);
          setCsvParsing(false);
          return;
        }
        
        setCsvData(parsedData);
        setCsvParsing(false);
        toast.success(`Successfully loaded ${parsedData.length} transaction(s) from CSV.`);
      } catch (error) {
        console.error("CSV parsing error:", error);
        toast.error(`Error reading CSV file: ${error instanceof Error ? error.message : 'Unknown error'}. Please check the format.`);
        setCsvFile(null);
        setCsvData([]);
        setCsvParsing(false);
      }
    };
    
    reader.onerror = () => {
      toast.error("Error reading file.");
      setCsvFile(null);
      setCsvData([]);
      setCsvParsing(false);
    };
    
    reader.onerror = () => {
      toast.error("Error reading file.");
      setCsvFile(null);
    };
    
    reader.readAsText(file);
  };

  // Batch Prediction
  const handleBatchPredict = async () => {
    if (csvData.length === 0) {
      toast.error("No CSV data to process.");
      return;
    }

    setBatchLoading(true);
    setBatchProgress(0);
    setBatchResults([]);
    setShowBatchResults(true);

    const results: BatchPredictionResult[] = [];
    let fraudCount = 0;
    let legitimateCount = 0;
    let errorCount = 0;

    for (let i = 0; i < csvData.length; i++) {
      const features = csvData[i];
      
      try {
        const response = await apiService.predictTransaction(features);
        
        results.push({
          transactionId: i + 1,
          prediction: response.prediction,
          probability: response.probability,
          status: 'success',
          transaction_id: response.transaction_id  // Store real transaction ID for SHAP
        });
        
        if (response.prediction === 'Fraudulent') {
          fraudCount++;
        } else {
          legitimateCount++;
        }
      } catch (error: unknown) {
        errorCount++;
        const errorMessage = error instanceof Error
          ? error.message
          : (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
          || 'Unknown error';
        results.push({
          transactionId: i + 1,
          prediction: 'Error',
          probability: 0,
          status: 'error',
          errorMessage
        });
      }

      // Update progress
      const progress = ((i + 1) / csvData.length) * 100;
      setBatchProgress(progress);
    }

    setBatchResults(results);
    setShowBatchResults(true);
    setBatchLoading(false);
    
    toast.success(
      `Batch prediction complete! Processed: ${csvData.length} transactions. ` +
      `Fraudulent: ${fraudCount}, Legitimate: ${legitimateCount}, Errors: ${errorCount}`
    );
  };

  // Download results as CSV
  const downloadResults = () => {
    if (batchResults.length === 0) return;

    const headers = ['Transaction_ID', 'Prediction', 'Probability', 'Status'];
    const rows = batchResults.map(r => [
      r.transactionId.toString(),
      r.prediction,
      r.status === 'success' ? `${r.probability.toFixed(2)}%` : 'N/A',
      r.status === 'error' ? r.errorMessage || 'Error' : 'Success'
    ]);

    const csvContent = [
      headers.join(','),
      ...rows.map(row => row.join(','))
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `fraud_predictions_${new Date().toISOString().split('T')[0]}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    
    toast.success("Results downloaded successfully!");
  };

  const parsePastedFeatures = (text: string): number[] | null => {
    if (!text || !text.trim()) {
      return null;
    }

    // Remove extra whitespace and split by comma, semicolon, or whitespace
    const cleaned = text.trim().replace(/\s+/g, ' ');
    const values = cleaned.split(/[,\s;]+/).filter(v => v.length > 0);

    if (values.length === 0) {
      setParseError("No values found. Please paste comma-separated or space-separated numbers.");
      return null;
    }

    // Convert to numbers
    const features = values.map(v => {
      const num = parseFloat(v.trim());
      return isNaN(num) ? 0 : num;
    });

    // Validate count
    if (features.length !== 30) {
      setParseError(`Expected 30 features, got ${features.length}. Format: Time, V1, V2, ..., V28, Amount`);
      return null;
    }

    setParseError(null);
    return features;
  };

  const handlePasteChange = (text: string) => {
    setPastedFeatures(text);
    setParseError(null);
    
    // Auto-parse and validate on paste
    if (text.trim()) {
      parsePastedFeatures(text);
    }
  };

  const handlePredict = async () => {
    // Parse pasted features
    const features = parsePastedFeatures(pastedFeatures);
    
    if (!features) {
      if (!parseError) {
        toast.error("Please paste transaction features (30 comma-separated values)");
      } else {
        toast.error(parseError);
      }
      return;
    }

    // Check for NaN values
    if (features.some(isNaN)) {
      toast.error("Please enter valid numeric values for all features");
      return;
    }

    setLoading(true);
    setResult(null);

    try {
      const response = await apiService.predictTransaction(features);
      setResult({
        prediction: response.prediction,
        probability: response.probability,
        threshold_used: response.threshold_used,
        transaction_id: response.transaction_id,
      });
      toast.success("Prediction completed!");
      } catch (error: unknown) {
        console.error("Prediction error:", error);
        const errorMessage = error instanceof Error 
          ? error.message 
          : (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail 
          || "Failed to make prediction";
        toast.error(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setPastedFeatures("");
    setParseError(null);
    setResult(null);
    // Clear sessionStorage for paste center
    sessionStorage.removeItem('manualPrediction_pasteResult');
    sessionStorage.removeItem('manualPrediction_pastedFeatures');
  };

  const isFraudulent = result?.prediction === "Fraudulent";
  // Probability is already in percentage (0-100) from API
  const riskPercentage = result ? result.probability.toFixed(2) : "0";
  const riskLevel = result ? (result.probability >= 70 ? "High" : result.probability >= 50 ? "Medium" : "Low") : "N/A";

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="container px-4 py-8 max-w-6xl">
        <div className="space-y-6">
          <div>
            <h1 className="text-3xl font-bold">Manual Transaction Prediction</h1>
            <p className="text-muted-foreground">
              Enter transaction features to predict fraud risk
            </p>
          </div>

          {/* CSV Upload Section */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Upload className="h-5 w-5" />
                Upload CSV File for Batch Prediction
              </CardTitle>
              <CardDescription>
                Upload a CSV file containing transactions. Each row should have 30 features: Time, V1-V28, Amount.
                Only CSV files are accepted.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center gap-4">
                <div className="flex-1">
                  <Input
                    type="file"
                    accept=".csv"
                    onChange={handleFileChange}
                    className="cursor-pointer"
                  />
                </div>
                {csvFile && (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <FileText className="h-4 w-4" />
                    <span>{csvFile.name}</span>
                    {csvParsing ? (
                      <span className="text-xs flex items-center gap-1">
                        <Loader2 className="h-3 w-3 animate-spin" />
                        Parsing...
                      </span>
                    ) : (
                      <span className="text-xs">({csvData.length} transactions)</span>
                    )}
                  </div>
                )}
              </div>

              {csvData.length > 0 && (
                <>
                  <Alert>
                    <AlertDescription>
                      ✅ CSV file loaded successfully! Found {csvData.length} transactions ready for prediction.
                    </AlertDescription>
                  </Alert>

                  <div className="flex gap-2">
                    <Button
                      onClick={handleBatchPredict}
                      disabled={batchLoading}
                      className="flex-1"
                    >
                      {batchLoading ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          Processing...
                        </>
                      ) : (
                        <>
                          <Upload className="mr-2 h-4 w-4" />
                          Predict All Transactions
                        </>
                      )}
                    </Button>
                    {batchResults.length > 0 && (
                      <Button
                        variant="outline"
                        onClick={downloadResults}
                      >
                        <Download className="mr-2 h-4 w-4" />
                        Download Results
                      </Button>
                    )}
                  </div>

                  {batchLoading && (
                    <div className="space-y-2">
                      <div className="flex justify-between text-sm">
                        <span>Processing transactions...</span>
                        <span>{Math.round(batchProgress)}%</span>
                      </div>
                      <Progress value={batchProgress} />
                    </div>
                  )}

                  {showBatchResults && batchResults.length > 0 && (
                    <div className="space-y-4">
                      <div className="grid grid-cols-4 gap-4">
                        <div className="p-4 bg-muted rounded-lg text-center">
                          <div className="text-2xl font-bold">{batchResults.length}</div>
                          <div className="text-sm text-muted-foreground">Total</div>
                        </div>
                        <div className="p-4 bg-red-50 dark:bg-red-950 rounded-lg text-center">
                          <div className="text-2xl font-bold text-red-600 dark:text-red-400">
                            {batchResults.filter(r => r.prediction === 'Fraudulent').length}
                          </div>
                          <div className="text-sm text-muted-foreground">Fraudulent</div>
                        </div>
                        <div className="p-4 bg-green-50 dark:bg-green-950 rounded-lg text-center">
                          <div className="text-2xl font-bold text-green-600 dark:text-green-400">
                            {batchResults.filter(r => r.prediction === 'Legitimate').length}
                          </div>
                          <div className="text-sm text-muted-foreground">Legitimate</div>
                        </div>
                        <div className="p-4 bg-yellow-50 dark:bg-yellow-950 rounded-lg text-center">
                          <div className="text-2xl font-bold text-yellow-600 dark:text-yellow-400">
                            {batchResults.filter(r => r.status === 'error').length}
                          </div>
                          <div className="text-sm text-muted-foreground">Errors</div>
                        </div>
                      </div>

                      <div className="border rounded-lg overflow-hidden">
                        <div className="max-h-96 overflow-y-auto">
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead>ID</TableHead>
                                <TableHead>Prediction</TableHead>
                                <TableHead>Probability</TableHead>
                                <TableHead>Status</TableHead>
                                <TableHead>Actions</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {batchResults.map((result) => (
                                <TableRow 
                                  key={result.transactionId}
                                  className={result.status === 'success' ? 'cursor-pointer hover:bg-muted/50' : ''}
                                  onClick={() => {
                                    if (result.status === 'success' && csvData[result.transactionId - 1]) {
                                      // Use real transaction_id if available, otherwise create temporary one
                                      const transactionId = result.transaction_id || `batch-${result.transactionId}-${Date.now()}`;
                                      
                                      // Create a transaction object from batch result
                                      const features = csvData[result.transactionId - 1];
                                      const transactionData = {
                                        id: transactionId,
                                        amount: features[features.length - 1], // Last feature is Amount
                                        timestamp: new Date().toISOString(),
                                        risk_score: result.probability,
                                        status: result.prediction === 'Fraudulent' ? 'flagged' : 'clear',
                                        prediction: result.prediction,
                                        features: features,
                                        probability: result.probability / 100 // Convert percentage to decimal
                                      };
                                      
                                      // Navigate to transaction details with data
                                      navigate(`/transactions/${transactionId}`, {
                                        state: {
                                          transaction: transactionData,
                                          from: '/manual-prediction'
                                        }
                                      });
                                    }
                                  }}
                                >
                                  <TableCell>{result.transactionId}</TableCell>
                                  <TableCell>
                                    <Badge
                                      variant={result.prediction === 'Fraudulent' ? 'destructive' : 'default'}
                                      className={result.prediction === 'Legitimate' ? 'bg-green-600' : ''}
                                    >
                                      {result.prediction}
                                    </Badge>
                                  </TableCell>
                                  <TableCell>
                                    {result.status === 'success' ? `${result.probability.toFixed(2)}%` : 'N/A'}
                                  </TableCell>
                                  <TableCell>
                                    {result.status === 'error' ? (
                                      <span className="text-red-600 text-xs">
                                        {result.errorMessage?.substring(0, 50)}...
                                      </span>
                                    ) : (
                                      <div className="flex items-center gap-2">
                                        <CheckCircle className="h-4 w-4 text-green-600" />
                                        <span className="text-xs text-muted-foreground">Click row to view</span>
                                      </div>
                                    )}
                                  </TableCell>
                                  <TableCell>
                                    {result.status === 'success' && result.transaction_id ? (
                                      <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          navigate(`/transactions/${result.transaction_id}`, {
                                            state: {
                                              from: '/manual-prediction',
                                              preserveBatchResults: true
                                            }
                                          });
                                        }}
                                      >
                                        View SHAP
                                      </Button>
                                    ) : (
                                      <span className="text-xs text-muted-foreground">—</span>
                                    )}
                                  </TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </div>
                      </div>
                    </div>
                  )}
                </>
              )}
            </CardContent>
          </Card>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Input Form */}
            <Card>
              <CardHeader>
                <CardTitle>Single Transaction Prediction</CardTitle>
                <CardDescription>
                  Paste a single transaction row with 30 comma-separated features
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                {/* Paste Center */}
                <div className="space-y-2">
                  <Label htmlFor="pasted-features">
                    Paste Transaction Features
                  </Label>
                  <p className="text-sm text-muted-foreground">
                    Paste a single transaction row with 30 comma-separated values: <br />
                    <code className="text-xs bg-muted px-1 py-0.5 rounded">Time, V1, V2, V3, ..., V28, Amount</code>
                  </p>
                  <Textarea
                    id="pasted-features"
                    placeholder="Example: 121958, 0.279, -0.428, -0.600, ..., -0.202, 31.17"
                    value={pastedFeatures}
                    onChange={(e) => handlePasteChange(e.target.value)}
                    className="font-mono text-sm min-h-[120px]"
                    rows={5}
                  />
                  {parseError && (
                    <Alert variant="destructive">
                      <AlertDescription className="text-sm">
                        {parseError}
                      </AlertDescription>
                    </Alert>
                  )}
                  {pastedFeatures && !parseError && (
                    <Alert>
                      <AlertDescription className="text-sm text-green-600 dark:text-green-400">
                        ✅ Valid format detected: 30 features ready for prediction
                      </AlertDescription>
                    </Alert>
                  )}
                </div>

                {/* Actions */}
                <div className="flex gap-2">
                  <Button
                    onClick={handlePredict}
                    disabled={loading}
                    className="flex-1"
                  >
                    {loading ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Predicting...
                      </>
                    ) : (
                      "Predict Fraud Risk"
                    )}
                  </Button>
                  <Button
                    variant="outline"
                    onClick={handleReset}
                    disabled={loading}
                  >
                    Reset
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* Result Card */}
            <Card>
              <CardHeader>
                <CardTitle>Prediction Result</CardTitle>
                <CardDescription>
                  Fraud detection analysis results
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                {!result ? (
                  <div className="flex flex-col items-center justify-center h-64 text-muted-foreground">
                    <Clipboard className="h-12 w-12 mb-4 opacity-50" />
                    <p>Paste transaction features above and click "Predict Fraud Risk"</p>
                    <p className="text-xs mt-2">Format: 30 comma-separated values (Time, V1-V28, Amount)</p>
                  </div>
                ) : (
                  <>
                    {/* Prediction Status */}
                    <Alert variant={isFraudulent ? "destructive" : "default"}>
                      <div className="flex items-start gap-3">
                        {isFraudulent ? (
                          <AlertTriangle className="h-5 w-5 mt-0.5" />
                        ) : (
                          <CheckCircle className="h-5 w-5 mt-0.5 text-green-600" />
                        )}
                        <div className="flex-1">
                          <AlertDescription>
                            <div className="flex items-center justify-between">
                              <span className="font-semibold">
                                Prediction: {result.prediction}
                              </span>
                              <Badge
                                variant={isFraudulent ? "destructive" : "default"}
                                className={!isFraudulent ? "bg-green-600" : ""}
                              >
                                {riskLevel} Risk
                              </Badge>
                            </div>
                          </AlertDescription>
                        </div>
                      </div>
                    </Alert>

                    {/* Risk Score */}
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <Label>Fraud Probability</Label>
                        <span className="text-2xl font-bold">
                          {riskPercentage}%
                        </span>
                      </div>
                      <div className="h-3 bg-muted rounded-full overflow-hidden">
                        <div
                          className={`h-full transition-all ${
                            isFraudulent ? "bg-destructive" : "bg-green-600"
                          }`}
                          style={{ width: `${riskPercentage}%` }}
                        />
                      </div>
                    </div>

                    {/* Details */}
                    <div className="space-y-2 p-4 bg-muted rounded-lg">
                      <div className="flex justify-between text-sm">
                        <span className="text-muted-foreground">Threshold Used:</span>
                        <span className="font-medium">
                          {result.threshold_used.toFixed(1)}%
                        </span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-muted-foreground">Risk Level:</span>
                        <span className="font-medium">{riskLevel}</span>
                      </div>
                    </div>

                    {/* Action Buttons */}
                    <div className="flex gap-2">
                      {result.transaction_id && (
                        <Button
                          className="flex-1"
                          onClick={() => navigate(`/transactions/${result.transaction_id}`, {
                            state: {
                              from: '/manual-prediction',
                              preservePasteResult: true
                            }
                          })}
                        >
                          View SHAP Explanation
                        </Button>
                      )}
                      <Button
                        variant="outline"
                        className={result.transaction_id ? "" : "flex-1"}
                        onClick={() => navigate("/transactions")}
                      >
                        View Transaction History
                      </Button>
                      <Button
                        variant="outline"
                        onClick={handleReset}
                      >
                        New Prediction
                      </Button>
                    </div>
                  </>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </main>
    </div>
  );
}

