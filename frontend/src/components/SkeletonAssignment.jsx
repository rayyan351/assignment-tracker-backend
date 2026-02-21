import "../styles/Skeleton.css";

export default function SkeletonAssignment() {
  return (
    <div className="skeleton-grid">
      {[...Array(6)].map((_, i) => (
        <div className="skeleton-card" key={i}>
          <div className="skeleton-line title"></div>
          <div className="skeleton-line"></div>
          <div className="skeleton-line small"></div>
          <div className="skeleton-line small"></div>
        </div>
      ))}
    </div>
  );
}
