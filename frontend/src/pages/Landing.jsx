import { useNavigate } from "react-router-dom";
import "../styles/landing.css";

export default function Landing() {

  const navigate = useNavigate();

  return (
    <div className="landing">

      <div className="hero">

        <h1>Bahria LMS Tracker</h1>

        <p>
          Automatically track assignments, monitor attendance,
          and receive alerts before deadlines.
        </p>

        <div className="hero-buttons">
          <button onClick={() => navigate("/login")}>
            Login
          </button>

          <button
            className="secondary"
            onClick={() => navigate("/register")}
          >
            Register
          </button>
        </div>

      </div>

    </div>
  );
}
