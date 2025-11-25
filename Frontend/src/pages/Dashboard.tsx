import { Header } from "@/components/layout/Header";
import { StatCard } from "@/components/dashboard/StatCard";
import { TransactionTable, Transaction } from "@/components/dashboard/TransactionTable";
import { Activity, AlertTriangle, TrendingUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { toast } from "sonner";
import React, { useEffect, useState, useMemo } from "react";
import { apiService, TransactionResponse } from "@/services/api";
import { useNavigate } from "react-router-dom";
import { PieChart, Pie, Cell, Legend } from "recharts";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";

export default function Dashboard() {
  type Stats = {
    total_predictions: number;
    fraud_detected: number;
    fraud_ratio: number;
  };
  const navigate = useNavigate();
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const transactionsPerPage = 15;

  // Convert backend transaction to frontend Transaction format
  const convertTransaction = (backendTx: TransactionResponse): Transaction => {
    try {
      // Handle missing or invalid timestamp
      let timeAgo = "Unknown";
      if (backendTx.timestamp) {
        try {
          const date = new Date(backendTx.timestamp);
          if (!isNaN(date.getTime())) {
            const now = new Date();
            const diffMs = now.getTime() - date.getTime();
            const diffMins = Math.floor(diffMs / 60000);
            
            if (diffMins < 1) timeAgo = "Just now";
            else if (diffMins < 60) timeAgo = `${diffMins}m ago`;
            else if (diffMins < 1440) timeAgo = `${Math.floor(diffMins / 60)}h ago`;
            else timeAgo = `${Math.floor(diffMins / 1440)}d ago`;
          }
        } catch (e) {
          console.warn("Error parsing timestamp:", e);
        }
      }

      // Use flagged status if transaction is flagged, otherwise use risk-based status
      let status: "clear" | "flagged" | "review" = "clear";
      if (backendTx.flagged) {
        status = "flagged";
      } else if (backendTx.status) {
        // Map backend status to frontend status
        const backendStatus = backendTx.status.toLowerCase();
        if (backendStatus === "flagged") {
          status = "flagged";
        } else if (backendStatus === "review") {
          status = "review";
        } else {
          status = "clear";
        }
      } else {
        // Fallback: use risk score to determine status
        const riskScore = backendTx.risk_score || 0;
        if (riskScore >= 70) {
          status = "flagged";
        } else if (riskScore >= 50) {
          status = "review";
        } else {
          status = "clear";
        }
      }

      return {
        id: backendTx.id || "unknown",
        amount: backendTx.amount || 0,
        time: timeAgo,
        riskScore: backendTx.risk_score || 0,
        status: status,
      };
    } catch (error) {
      console.error("Error converting transaction:", error, backendTx);
      // Return a safe default transaction
      return {
        id: backendTx?.id || "error",
        amount: backendTx?.amount || 0,
        time: "Unknown",
        riskScore: backendTx?.risk_score || 0,
        status: "clear",
      };
    }
  };

  useEffect(() => {
    // Check if we should show welcome notification after successful login
    const showWelcome = sessionStorage.getItem("showWelcomeNotification");
    if (showWelcome === "true") {
      // Clear the flag so it doesn't show again on refresh
      sessionStorage.removeItem("showWelcomeNotification");
      // Show welcome notification at the top
      setTimeout(() => {
        toast.success("Welcome to FraudDetectPro Dashboard!", {
          duration: 4000,
          position: "top-center",
        });
      }, 500);
    }

    // Initial load - fetch stats and existing transactions
    let initialLoad = true;
    const fetchInitialData = async () => {
      setLoading(true);
      try {
        const [statsData, transactionsData] = await Promise.all([
          apiService.getStats(),
          apiService.getTransactions(),
        ]);
        setStats(statsData);
        const convertedTransactions = transactionsData.map(convertTransaction);
        setTransactions(convertedTransactions);
        setError(null);
      } catch (e: unknown) {
        console.error("Failed to fetch initial data:", e);
        if (e instanceof Error) {
          setError(e.message || "Failed to fetch data");
        } else {
          setError("Failed to fetch data");
        }
        setStats({
          total_predictions: 0,
          fraud_detected: 0,
          fraud_ratio: 0
        });
        setTransactions([]);
      } finally {
        setLoading(false);
        initialLoad = false;
      }
    };
    fetchInitialData();

    // Set up real-time streaming via Server-Sent Events
    const apiBaseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    const token = localStorage.getItem('firebase_token') || '';
    
    const eventSource = new EventSource(`${apiBaseUrl}/api/transactions/stream`, {
      withCredentials: true
    });

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        if (data.type === 'connected') {
          console.log('✅ Connected to real-time transaction stream');
          return;
        }

        // New or updated transaction from data_generator.py or flag update
        const updatedTransaction = convertTransaction(data);
        
        // Update or add transaction
        setTransactions(prev => {
          // Check if transaction already exists
          const existingIndex = prev.findIndex(tx => tx.id === updatedTransaction.id);
          const isNewTransaction = existingIndex === -1;
          
          if (existingIndex >= 0) {
            // Update existing transaction (e.g., flag status changed)
            const updated = [...prev];
            updated[existingIndex] = updatedTransaction;
            return updated;
          } else {
            // Add new transaction to beginning
            const newList = [updatedTransaction, ...prev].slice(0, 100); // Keep last 100
            
            // Update stats only for new transactions
            if (isNewTransaction) {
              setStats(prevStats => {
                const newTotal = (prevStats?.total_predictions || 0) + 1;
                const newFraud = (prevStats?.fraud_detected || 0) + (updatedTransaction.status === 'flagged' ? 1 : 0);
                return {
                  total_predictions: newTotal,
                  fraud_detected: newFraud,
                  fraud_ratio: (newFraud / newTotal) * 100
                };
              });
            }
            
            return newList;
          }
        });
      } catch (e) {
        console.error('Error parsing SSE message:', e);
      }
    };

    eventSource.onerror = (error) => {
      console.error('SSE connection error:', error);
      // Fallback to polling if SSE fails
      const fallbackInterval = setInterval(async () => {
        try {
          const transactionsData = await apiService.getTransactions();
          const convertedTransactions = transactionsData.map(convertTransaction);
          setTransactions(convertedTransactions);
        } catch (e) {
          console.error('Fallback polling error:', e);
        }
      }, 5000);
      
      return () => clearInterval(fallbackInterval);
    };

    // Cleanup
    return () => {
      eventSource.close();
    };
  }, []);

  const handleViewDetails = (id: string) => {
    navigate(`/transactions/${id}`, { state: { from: "/dashboard" } });
    toast.info(`Viewing details for transaction ${id.slice(0, 12)}...`);
  };

  const handleFlag = (id: string) => {
    // Navigate to transaction details where user can flag/unflag
    navigate(`/transactions/${id}`, { state: { from: "/dashboard" } });
  };

  // Calculate risk distribution for pie chart
  const riskDistribution = useMemo(() => {
    const highRisk = transactions.filter((t) => t.riskScore >= 70).length;
    const mediumRisk = transactions.filter((t) => t.riskScore >= 40 && t.riskScore < 70).length;
    const lowRisk = transactions.filter((t) => t.riskScore < 40).length;

    return [
      { name: "High Risk", value: highRisk, color: "#ef4444" }, // red-500
      { name: "Medium Risk", value: mediumRisk, color: "#f59e0b" }, // amber-500
      { name: "Low Risk", value: lowRisk, color: "#10b981" }, // emerald-500
    ];
  }, [transactions]);

  const chartConfig = {
    "High Risk": {
      label: "High Risk (70-100)",
      color: "#ef4444",
    },
    "Medium Risk": {
      label: "Medium Risk (40-69)",
      color: "#f59e0b",
    },
    "Low Risk": {
      label: "Low Risk (0-39)",
      color: "#10b981",
    },
  };

  // Pagination calculations
  const totalPages = Math.ceil(transactions.length / transactionsPerPage);
  const startIndex = (currentPage - 1) * transactionsPerPage;
  const endIndex = startIndex + transactionsPerPage;
  const paginatedTransactions = transactions.slice(startIndex, endIndex);

  // Reset to page 1 when transactions change
  useEffect(() => {
    setCurrentPage(1);
  }, [transactions.length]);

  if (loading) return <div className="min-h-screen flex items-center justify-center">Loading dashboard...</div>;
  if (error) return <div className="min-h-screen flex items-center justify-center text-destructive">Error: {error}</div>;
  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="container px-4 py-8">
        {/* Hero Metrics */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
          <StatCard
            title="Total Transactions"
            value={stats ? stats.total_predictions.toLocaleString() : "-"}
            trend={{ value: "", isPositive: true }}
            icon={<Activity className="h-6 w-6" />}
          />
          <StatCard
            title="Fraud Cases Detected"
            value={stats ? stats.fraud_detected.toLocaleString() : "-"}
            trend={{ value: "", isPositive: true }}
            icon={<AlertTriangle className="h-6 w-6" />}
          />
          <StatCard
            title="Fraud Ratio"
            value={stats ? `${stats.fraud_ratio.toFixed(3)}%` : "-"}
            trend={{ value: "", isPositive: true }}
            icon={<TrendingUp className="h-6 w-6" />}
          />
        </div>
        {/* Main Content Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Transaction Feed */}
          <div className="lg:col-span-2 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-2xl font-bold">Real-Time Transactions</h2>
                <p className="text-sm text-muted-foreground">Live feed of all payment activities</p>
              </div>
              <Button variant="outline">Export</Button>
            </div>
            <TransactionTable
              transactions={paginatedTransactions}
              onViewDetails={handleViewDetails}
              onFlag={handleFlag}
            />
            <div className="flex items-center justify-between text-sm text-muted-foreground">
              <p>
                Showing {transactions.length > 0 ? startIndex + 1 : 0}-
                {Math.min(endIndex, transactions.length)} of {transactions.length} transactions
                {stats && ` (Total: ${stats.total_predictions.toLocaleString()})`}
              </p>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setCurrentPage((prev) => Math.max(1, prev - 1))}
                  disabled={currentPage === 1}
                >
                  Previous
                </Button>
                <span className="text-xs">
                  Page {currentPage} of {totalPages || 1}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setCurrentPage((prev) => Math.min(totalPages, prev + 1))}
                  disabled={currentPage >= totalPages || transactions.length === 0}
                >
                  Next
                </Button>
              </div>
            </div>
          </div>
          {/* Quick Insights */}
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-semibold mb-4">Quick Insights</h3>
              {/* Risk Distribution Pie Chart */}
              <div className="rounded-lg border border-border bg-card p-6">
                <h4 className="font-semibold mb-4">Transaction Risk Distribution</h4>
                {transactions.length === 0 ? (
                  <div className="h-48 flex items-center justify-center text-muted-foreground text-sm">
                    No transactions to display
                  </div>
                ) : (
                  <div className="w-full h-64 overflow-hidden">
                    <ChartContainer config={chartConfig} className="h-full w-full">
                      <PieChart>
                        <ChartTooltip 
                          content={<ChartTooltipContent />}
                          formatter={(value: number, name: string) => [
                            `${value} transactions`,
                            chartConfig[name as keyof typeof chartConfig]?.label || name
                          ]}
                        />
                        <Pie
                          data={riskDistribution}
                          dataKey="value"
                          nameKey="name"
                          cx="50%"
                          cy="45%"
                          outerRadius={70}
                          label={({ value, percent }) => 
                            value > 0 ? `${(percent * 100).toFixed(1)}%` : ""
                          }
                          labelLine={false}
                        >
                          {riskDistribution.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={entry.color} />
                          ))}
                        </Pie>
                        <Legend
                          verticalAlign="bottom"
                          height={36}
                          formatter={(value) => {
                            const config = chartConfig[value as keyof typeof chartConfig];
                            return config?.label || value;
                          }}
                        />
                      </PieChart>
                    </ChartContainer>
                  </div>
                )}
              </div>
            </div>
            {/* Top High-Risk Transactions */}
            <div>
              <h4 className="font-semibold mb-4">Top High-Risk Today</h4>
              <div className="space-y-3">
                {transactions.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No high-risk transactions found</p>
                ) : (
                  transactions
                    .filter((t) => t.riskScore > 70)
                    .slice(0, 3)
                    .map((t) => (
                    <div
                      key={t.id}
                      className="rounded-lg border-l-4 border-destructive bg-card p-4 hover:bg-muted/30 transition-colors cursor-pointer"
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-mono text-xs text-muted-foreground">
                          {t.id.slice(0, 12)}...
                        </span>
                        <span className="text-sm font-bold text-destructive">{t.riskScore.toFixed(2)}%</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="font-semibold">${t.amount.toLocaleString()}</span>
                        <span className="text-xs text-muted-foreground">{t.time}</span>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}