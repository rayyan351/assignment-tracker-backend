import { useEffect, useState } from "react";
import { api } from "../api/api";
import "../styles/attendance.css";

export default function Attendance() {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const fetchAttendance = async () => {
      try {
        const res = await api("/attendance");
        setData(res.attendance || []);
      } catch (err) {
        setError("Failed to load attendance");
      } finally {
        setLoading(false);
      }
    };

    fetchAttendance();
  }, []);

  if (loading) return <p>Loading attendance...</p>;
  if (error) return <p className="error">{error}</p>;

  return (
    <div className="attendance-wrapper">
      <h2>Your Attendance</h2>

      <table className="attendance-table">
        <thead>
          <tr>
            <th>Course</th>
            <th>Present</th>
            <th>Total</th>
            <th>Percentage</th>
          </tr>
        </thead>

        <tbody>
          {data.map((course, i) => (
            <tr key={i}>
              <td>{course.course}</td>
              <td>{course.present}</td>
              <td>{course.total}</td>
              <td>
                <span
                  className={
                    course.percentage >= 80
                      ? "good"
                      : course.percentage >= 60
                      ? "average"
                      : "danger"
                  }
                >
                  {course.percentage}%
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
