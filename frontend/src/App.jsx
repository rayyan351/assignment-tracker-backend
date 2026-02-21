import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import { useEffect, useState } from "react";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Dashboard from "./pages/Dashboard";
import Loader from "./components/Loader";
import Landing from "./pages/Landing";

const PrivateRoute = ({ children }) => {
  return localStorage.getItem("token")
    ? children
    : <Navigate to="/" />;
};

export default function App() {
    const [loading, setLoading] = useState(true);

  useEffect(() => {

    const timer = setTimeout(() => {
      setLoading(false);
    }, 1500);

    return () => clearTimeout(timer);

  }, []);

  if (loading) return <Loader />;
  return (
    <>
      <Toaster
       position="top-right"
        toastOptions={{
          duration: 3000,
        }}
      />
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route
            path="/dashboard"
            element={
              <PrivateRoute>
                <Dashboard />
              </PrivateRoute>
            }
          />
        </Routes>
      </BrowserRouter>
    </>
  );
}
