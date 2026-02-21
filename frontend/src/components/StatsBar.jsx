import { useEffect, useState } from "react";
import "../styles/StatsBar.css";

function AnimatedNumber({ value }) {
  const [count, setCount] = useState(0);

  useEffect(() => {
    let start = 0;
    const step = () => {
      start += Math.ceil((value - start) / 6);
      if (start >= value) return setCount(value);
      setCount(start);
      requestAnimationFrame(step);
    };
    step();
  }, [value]);

  return <span className="stat-number">{count}</span>;
}

export default function StatsBar({ stats, onFilter, active }) {
  return (
    <div className="stats-bar">
      <div className={`stat-card ${active === "all" ? "active" : ""}`} onClick={() => onFilter("all")}>
        <AnimatedNumber value={stats.total} />
        <span className="stat-label">Total</span>
      </div>

      <div className={`stat-card warning ${active === "due" ? "active" : ""}`} onClick={() => onFilter("due")}>
        <AnimatedNumber value={stats.dueSoon} />
        <span className="stat-label">Due Soon</span>
      </div>

      <div className={`stat-card danger ${active === "overdue" ? "active" : ""}`} onClick={() => onFilter("overdue")}>
        <AnimatedNumber value={stats.overdue} />
        <span className="stat-label">Overdue</span>
      </div>
    </div>
  );
}
