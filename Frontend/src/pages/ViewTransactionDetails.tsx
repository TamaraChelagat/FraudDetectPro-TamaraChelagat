import { useEffect, useState } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import { Header } from "@/components/layout/Header";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ArrowLeft, AlertTriangle, CheckCircle2, Clock, TrendingUp, TrendingDown, Flag } from "lucide-react";
import { apiService, SHAPExplanationResponse, TransactionResponse, FlagTransactionRequest } from "@/services/api";
import { toast } from "sonner";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

export default function ViewTransactionDetails() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const [transaction, setTransaction] = useState<TransactionResponse | null>(null);
  const [explanation, setExplanation] = useState<SHAPExplanationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [explanationLoading, setExplanationLoading] = useState(true);
  const [flagModalOpen, setFlagModalOpen] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [flagging, setFlagging] = useState(false);

  // Get the return path from location state, default to /transactions
  const returnPath = (location.state as { from?: string })?.from || "/transactions";

  useEffect(() => {
    // Check if transaction data was passed via navigation state (e.g., from batch predictions)
    const locationState = location.state as { transaction?: TransactionResponse; from?: string } | null;
    if (locationState?.transaction) {
      setTransaction(locationState.transaction);
      setLoading(false);
      // Try to fetch explanation if transaction ID exists
      // Now batch predictions also have real transaction IDs, so we can fetch SHAP for all
      if (id) {
        (async () => {
          try {
            setExplanationLoading(true);
            const exp = await apiService.getTransactionExplanation(id);
            setExplanation(exp);
          } catch (error: unknown) {
            console.error("Failed to fetch SHAP explanation:", error);
            // Only show error if it's not a batch ID (batch IDs might not have SHAP)
            if (!id.startsWith('batch-')) {
              toast.error("Failed to load SHAP explanation");
            }
          } finally {
            setExplanationLoading(false);
          }
        })();
      } else {
        setExplanationLoading(false);
      }
      return;
    }

    if (!id) {
      toast.error("Transaction ID not provided");
      navigate(returnPath);
      return;
    }

    const fetchData = async () => {
      try {
        setLoading(true);
        const tx = await apiService.getTransaction(id);
        setTransaction(tx);
      } catch (error: unknown) {
        console.error("Failed to fetch transaction:", error);
        const errorMessage = error instanceof Error 
          ? error.message 
          : (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail 
          || "Failed to load transaction details";
        toast.error(errorMessage);
        navigate(returnPath);
      } finally {
        setLoading(false);
      }

      try {
        setExplanationLoading(true);
        const exp = await apiService.getTransactionExplanation(id);
        setExplanation(exp);
      } catch (error: unknown) {
        console.error("Failed to fetch SHAP explanation:", error);
        const errorMessage = error instanceof Error 
          ? error.message 
          : (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail 
          || "Failed to load SHAP explanation";
        toast.error(errorMessage);
      } finally {
        setExplanationLoading(false);
      }
    };

    fetchData();
  }, [id, navigate, returnPath, location.state]);

  const getStatusBadge = (status: string) => {
    const variants: Record<string, "default" | "destructive" | "secondary" | "outline"> = {
      clear: "default",
      flagged: "destructive",
      review: "secondary",
    };
    
    const labels: Record<string, string> = {
      clear: "Clear",
      flagged: "Flagged",
      review: "Under Review",
    };

    const icons: Record<string, React.ComponentType<{ className?: string }>> = {
      clear: CheckCircle2,
      flagged: AlertTriangle,
      review: Clock,
    };

    const Icon = icons[status] || CheckCircle2;

    return (
      <Badge variant={variants[status] || "default"} className="flex items-center gap-1">
        <Icon className="h-3 w-3" />
        {labels[status] || status}
      </Badge>
    );
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const handleFlagTransaction = () => {
    if (!transaction) return;
    setFeedback(transaction.feedback || "");
    setFlagModalOpen(true);
  };

  const handleSubmitFlag = async () => {
    if (!transaction) return;

    const isCurrentlyFlagged = transaction.flagged || false;
    const newFlagStatus = !isCurrentlyFlagged;

    // If unflagging and no feedback provided, that's fine
    // If flagging, feedback is optional but recommended
    if (newFlagStatus && !feedback.trim()) {
      toast.warning("Please provide feedback when flagging a transaction");
      return;
    }

    setFlagging(true);
    try {
      const request: FlagTransactionRequest = {
        flagged: newFlagStatus,
        feedback: feedback.trim() || undefined,
      };

      const response = await apiService.flagTransaction(transaction.id, request);

      if (response.success) {
        // Update local transaction state
        // When flagging, set status to "flagged"
        // When unflagging, restore original status based on risk score
        let newStatus = transaction.status;
        if (response.flagged) {
          newStatus = "flagged";
        } else {
          // Restore original status based on risk score
          const riskScore = transaction.risk_score || 0;
          if (riskScore >= 70) {
            newStatus = "flagged";
          } else if (riskScore >= 50) {
            newStatus = "review";
          } else {
            newStatus = "clear";
          }
        }
        
        setTransaction({
          ...transaction,
          flagged: response.flagged,
          feedback: feedback.trim() || undefined,
          analyst_email: response.flagged ? (transaction.analyst_email || "current_user") : undefined,
          status: newStatus,
        });

        toast.success(
          `Transaction ${response.flagged ? "flagged" : "unflagged"} successfully`,
          { duration: 3000 }
        );
        setFlagModalOpen(false);
        setFeedback("");
      } else {
        toast.error("Failed to update transaction flag status");
      }
    } catch (error: unknown) {
      console.error("Flag transaction error:", error);
      const errorMessage =
        error instanceof Error
          ? error.message
          : (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
            "Failed to update transaction flag status";
      toast.error(errorMessage);
    } finally {
      setFlagging(false);
    }
  };

  // Sort SHAP values by absolute value (most important features first)
  const topFeatures = explanation
    ? explanation.shap_values
        .map((value, index) => ({
          name: explanation.feature_names[index] || `Feature ${index}`,
          shap_value: value,
          feature_value: explanation.feature_values[index],
          index,
        }))
        .sort((a, b) => Math.abs(b.shap_value) - Math.abs(a.shap_value))
        .slice(0, 15) // Top 15 features
    : [];

  if (loading) {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <main className="container px-4 py-8">
          <Skeleton className="h-12 w-64 mb-4" />
          <Skeleton className="h-96 w-full" />
        </main>
      </div>
    );
  }

  if (!transaction) {
    return null;
  }

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="container px-4 py-8 max-w-7xl mx-auto">
        <div className="space-y-6">
          {/* Header */}
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <Button variant="ghost" size="icon" onClick={() => navigate(returnPath)}>
                <ArrowLeft className="h-4 w-4" />
              </Button>
              <div>
                <h1 className="text-3xl font-bold">Transaction Details</h1>
                <p className="text-muted-foreground font-mono text-sm">{transaction.id}</p>
              </div>
            </div>
            <Button
              variant={transaction.flagged ? "default" : "destructive"}
              onClick={handleFlagTransaction}
              className="flex items-center gap-2"
            >
              <Flag className="h-4 w-4" />
              {transaction.flagged ? "Unflag Transaction" : "Flag Transaction"}
            </Button>
          </div>

          {/* Transaction Overview */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card className="p-6">
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">Amount</p>
                <p className="text-3xl font-bold">${transaction.amount.toLocaleString()}</p>
              </div>
            </Card>

            <Card className="p-6">
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">Risk Score</p>
                <div className="flex items-center gap-2">
                  <p className="text-3xl font-bold">{transaction.risk_score.toFixed(2)}%</p>
                  {transaction.risk_score >= 70 ? (
                    <TrendingUp className="h-6 w-6 text-destructive" />
                  ) : transaction.risk_score >= 50 ? (
                    <Clock className="h-6 w-6 text-yellow-500" />
                  ) : (
                    <TrendingDown className="h-6 w-6 text-green-500" />
                  )}
                </div>
              </div>
            </Card>

            <Card className="p-6">
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">Status</p>
                <div className="mt-2">{getStatusBadge(transaction.status)}</div>
                <p className="text-sm text-muted-foreground mt-2">
                  Prediction: <span className="font-semibold">{transaction.prediction}</span>
                </p>
              </div>
            </Card>
          </div>

          {/* Transaction Info */}
          <Card className="p-6">
            <h2 className="text-xl font-semibold mb-4">Transaction Information</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Transaction ID</p>
                <p className="font-mono text-sm mt-1">{transaction.id}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Timestamp</p>
                <p className="text-sm mt-1">{formatDate(transaction.timestamp)}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Prediction Probability</p>
                <p className="text-sm mt-1 font-semibold">
                  {((transaction.probability || transaction.risk_score / 100) * 100).toFixed(2)}%
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Risk Level</p>
                <p className="text-sm mt-1">
                  {transaction.risk_score >= 70
                    ? "High Risk"
                    : transaction.risk_score >= 50
                    ? "Medium Risk"
                    : "Low Risk"}
                </p>
              </div>
            </div>
          </Card>

          {/* SHAP Explanation */}
          <Card className="p-6">
            <h2 className="text-xl font-semibold mb-4">SHAP Explainability</h2>
            <p className="text-sm text-muted-foreground mb-6">
              This visualization shows which features contributed most to the fraud prediction. Positive values (red)
              increase fraud probability, while negative values (blue) decrease it.
            </p>

            {explanationLoading ? (
              <div className="space-y-4">
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
              </div>
            ) : explanation ? (
              <div className="space-y-4">
                {/* Base Value and Prediction */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                  <div className="p-4 bg-muted rounded-lg">
                    <p className="text-sm text-muted-foreground">Base Value</p>
                    <p className="text-lg font-semibold">{explanation.base_value.toFixed(4)}</p>
                  </div>
                  <div className="p-4 bg-muted rounded-lg">
                    <p className="text-sm text-muted-foreground">Final Prediction</p>
                    <p className="text-lg font-semibold">{explanation.prediction}</p>
                  </div>
                  <div className="p-4 bg-muted rounded-lg">
                    <p className="text-sm text-muted-foreground">Probability</p>
                    <p className="text-lg font-semibold">
                      {(explanation.prediction_probability * 100).toFixed(2)}%
                    </p>
                  </div>
                </div>

                {/* Top Features Waterfall */}
                <div className="space-y-2">
                  <h3 className="font-semibold mb-4">Top Contributing Features</h3>
                  {topFeatures.map((feature, index) => {
                    const isPositive = feature.shap_value > 0;
                    const absValue = Math.abs(feature.shap_value);
                    const maxAbs = Math.max(...topFeatures.map((f) => Math.abs(f.shap_value)));

                    return (
                      <div key={index} className="space-y-1">
                        <div className="flex items-center justify-between text-sm">
                          <span className="font-medium">{feature.name}</span>
                          <span className={`font-semibold ${isPositive ? "text-red-500" : "text-blue-500"}`}>
                            {feature.shap_value > 0 ? "+" : ""}
                            {feature.shap_value.toFixed(4)}
                          </span>
                        </div>
                        <div className="relative h-6 bg-muted rounded overflow-hidden">
                          <div
                            className={`absolute top-0 h-full ${isPositive ? "bg-red-500" : "bg-blue-500"} transition-all`}
                            style={{
                              width: `${(absValue / maxAbs) * 100}%`,
                              left: isPositive ? "0" : "auto",
                              right: isPositive ? "auto" : "0",
                            }}
                          />
                        </div>
                        <p className="text-xs text-muted-foreground ml-2">
                          Feature value: {feature.feature_value.toFixed(4)}
                        </p>
                      </div>
                    );
                  })}
                </div>

                {/* Feature Contribution Summary */}
                <div className="mt-6 p-4 bg-muted rounded-lg">
                  <h3 className="font-semibold mb-2">Summary</h3>
                  <p className="text-sm text-muted-foreground">
                    The model's prediction of{" "}
                    <span className="font-semibold">{explanation.prediction}</span> is based on{" "}
                    {topFeatures.filter((f) => f.shap_value > 0).length} features increasing fraud probability and{" "}
                    {topFeatures.filter((f) => f.shap_value < 0).length} features decreasing it. The total SHAP value
                    contribution is{" "}
                    <span className="font-semibold">
                      {topFeatures
                        .reduce((sum, f) => sum + f.shap_value, 0)
                        .toFixed(4)}
                    </span>
                    .
                  </p>
                </div>
              </div>
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                <p>SHAP explanation not available</p>
              </div>
            )}
          </Card>
        </div>
      </main>

      {/* Flag Transaction Modal */}
      <Dialog open={flagModalOpen} onOpenChange={setFlagModalOpen}>
        <DialogContent className="sm:max-w-[600px]">
          <DialogHeader>
            <DialogTitle>
              {transaction?.flagged ? "Unflag Transaction" : "Flag Transaction"}
            </DialogTitle>
            <DialogDescription>
              {transaction?.flagged
                ? "Provide feedback on why you are unflagging this transaction."
                : "Provide feedback on why you are flagging this transaction for review."}
            </DialogDescription>
          </DialogHeader>

          {transaction && (
            <div className="space-y-4 py-4">
              {/* Transaction Information (Read-only) */}
              <div className="space-y-2 p-4 bg-muted rounded-lg">
                <h4 className="font-semibold text-sm mb-3">Transaction Information</h4>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <p className="text-muted-foreground">Transaction ID</p>
                    <p className="font-mono text-xs">{transaction.id}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Amount</p>
                    <p className="font-semibold">${transaction.amount.toLocaleString()}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Timestamp</p>
                    <p className="text-xs">{formatDate(transaction.timestamp)}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Risk Score</p>
                    <p className="font-semibold">{transaction.risk_score.toFixed(2)}%</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Prediction</p>
                    <p className="font-semibold">{transaction.prediction}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Current Status</p>
                    <p>{getStatusBadge(transaction.status)}</p>
                  </div>
                </div>
              </div>

              {/* Feedback Input */}
              <div className="space-y-2">
                <Label htmlFor="feedback">
                  Feedback {transaction.flagged ? "(Optional)" : "(Recommended)"}
                </Label>
                <Textarea
                  id="feedback"
                  placeholder={
                    transaction.flagged
                      ? "Explain why you are unflagging this transaction..."
                      : "Explain why you are flagging this transaction (e.g., suspicious patterns, model disagreement, etc.)..."
                  }
                  value={feedback}
                  onChange={(e) => setFeedback(e.target.value)}
                  rows={5}
                  className="resize-none"
                />
                <p className="text-xs text-muted-foreground">
                  {transaction.flagged
                    ? "Optional: Provide context for unflagging this transaction."
                    : "Recommended: Explain the reason for flagging to help with review and model improvement."}
                </p>
              </div>
            </div>
          )}

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setFlagModalOpen(false);
                setFeedback("");
              }}
              disabled={flagging}
            >
              Cancel
            </Button>
            <Button onClick={handleSubmitFlag} disabled={flagging}>
              {flagging ? (
                <>
                  <Clock className="mr-2 h-4 w-4 animate-spin" />
                  Processing...
                </>
              ) : transaction?.flagged ? (
                "Unflag Transaction"
              ) : (
                "Flag Transaction"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}


