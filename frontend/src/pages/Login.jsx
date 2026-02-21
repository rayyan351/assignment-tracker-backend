import { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { api } from "../api/api";
import "../styles/auth.css";

export default function Login() {
  const navigate = useNavigate();

  const [enrollment, setEnrollment] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const location = useLocation();
  const successMessage = location.state?.success;


  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await api("/login", {
        method: "POST",
        body: JSON.stringify({ enrollment, password })
      });

      localStorage.setItem("token", res.token);
      navigate("/dashboard");
    } catch (err) {
      setError(err.message || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-wrapper">
      <form className="auth-card" onSubmit={submit}>
        <h1>Student Login</h1>
        <p>Bahria LMS Assignment Tracker</p>
        {successMessage && ( <div className="success-toast"> {successMessage} </div>)}
        {error && <div className="error">{error}</div>}

        <input
          type="text"
          placeholder="Enrollment No"
          value={enrollment}
          onChange={(e) => setEnrollment(e.target.value)}
          required
        />

        {/* PASSWORD FIELD WITH EYE */}
        <div className="password-wrapper">
          <input
            type={showPassword ? "text" : "password"}
            placeholder="CMS Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />

          <span
            className="eye"
            onClick={() => setShowPassword(!showPassword)}
          >
            {showPassword ? "👁️" : "👁️‍🗨️"}
          </span>
        </div>

        <button disabled={loading}>
          {loading ? "Signing in..." : "Login"}
        </button>

        <span className="link" onClick={() => navigate("/register")}>
          New here? Create account
        </span>
      </form>
    </div>
  );
}
