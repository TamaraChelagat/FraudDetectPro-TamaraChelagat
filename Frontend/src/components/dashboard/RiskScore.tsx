import { cn } from "@/lib/utils";

interface RiskScoreProps {
  score: number;
  className?: string;
}

export function RiskScore({ score, className }: RiskScoreProps) {
  const getRiskColor = (score: number) => {
    if (score <= 40) return "bg-success";
    if (score <= 70) return "bg-warning";
    return "bg-destructive";
  };

  const getRiskLabel = (score: number) => {
    if (score <= 40) return "Low";
    if (score <= 70) return "Medium";
    return "High";
  };

  const getTextColor = (score: number) => {
    if (score <= 40) return "text-success";
    if (score <= 70) return "text-warning";
    return "text-destructive";
  };

  return (
    <div className={cn("space-y-1", className)}>
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">Risk Score</span>
        <span className={cn("font-bold", getTextColor(score))}>{score.toFixed(2)}%</span>
      </div>
      <div className="h-2 bg-muted rounded-full overflow-hidden">
        <div
          className={cn("h-full transition-all duration-500", getRiskColor(score))}
          style={{ width: `${score}%` }}
        />
      </div>
      <span className={cn("text-xs font-semibold", getTextColor(score))}>
        {getRiskLabel(score)} Risk
      </span>
    </div>
  );
}
