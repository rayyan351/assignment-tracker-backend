import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/api";
import "../styles/auth.css";

export default function Register() {
  const navigate = useNavigate();

  const [enrollment, setEnrollment] = useState("");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      await api("/register", {
        method: "POST",
        body: JSON.stringify({ enrollment, password, email })
      });

      navigate("/", { state: { success: "Account created successfully" } });

    } catch (err) {
      setError(err.message || "Registration failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-wrapper">
      <form className="auth-card" onSubmit={submit}>
        <h1>Create Account</h1>
        <p>Use your CMS credentials</p>

        {error && <div className="error">{error}</div>}

        <input
          autoFocus
          type="text"
          placeholder="Enrollment No"
          value={enrollment}
          onChange={(e) => setEnrollment(e.target.value)}
          required
        />

        <input
          type="email"
          placeholder="Alert Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
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
          {loading ? "Creating..." : "Register"}
        </button>

        <span className="link" onClick={() => navigate("/login")}>
          Already have an account? Login
        </span>
      </form>
    </div>
  );
}
