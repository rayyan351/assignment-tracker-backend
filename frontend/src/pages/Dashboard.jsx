import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import SkeletonAssignment from "../components/SkeletonAssignment";
import StatsBar from "../components/StatsBar";
import toast from "react-hot-toast";
import { api } from "../api/api";
import "../styles/dashboard.css";

export default function Dashboard() {
  const navigate = useNavigate();

  const [assignments, setAssignments] = useState([]);
  const [attendance, setAttendance] = useState([]);

  const [loading, setLoading] = useState(true);
  const [attendanceLoading, setAttendanceLoading] = useState(false);

  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState("");

  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [sortCourse, setSortCourse] = useState("all");
  const [activeTab, setActiveTab] = useState("assignments");

  const previousSyncing = useRef(false);

  /* ---------------- LOAD ASSIGNMENTS ---------------- */
  const loadAssignments = async () => {
    try {
      const res = await api("/assignments");
      setAssignments(res.assignments || []);
      setError("");
    } catch {
      setError("Failed to load assignments");
    } finally {
      setLoading(false);
    }
  };

  /* ---------------- LOAD ATTENDANCE ---------------- */
  const loadAttendance = async () => {
    try {
      setAttendanceLoading(true);
      const res = await api("/attendance");
      setAttendance(res.attendance || []);
    } catch {
      toast.error("Failed to load attendance");
    } finally {
      setAttendanceLoading(false);
    }
  };

  /* ---------------- INITIAL LOAD ---------------- */
  useEffect(() => {
    loadAssignments();
  }, []);

  /* ---------------- CHECK INITIAL SYNC STATUS ---------------- */
  useEffect(() => {
    const checkInitialStatus = async () => {
      try {
        const res = await api("/sync/status");
        setSyncing(res.syncing);
      } catch {}
    };

    checkInitialStatus();
  }, []);

  /* ---------------- CONTROLLED SYNC POLLING ---------------- */
  useEffect(() => {
    if (!syncing) return;

    const interval = setInterval(async () => {
      try {
        const res = await api("/sync/status");

        if (!res.syncing) {
          setSyncing(false);
          loadAssignments();
          loadAttendance();
          toast.dismiss("syncToast");
          toast.success("Data updated successfully 🎉");
        }
      } catch {
        setSyncing(false);
        toast.dismiss("syncToast");
        toast.error("Sync failed. Please try again.");
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [syncing]);

  /* ---------------- MANUAL SYNC ---------------- */
  const syncLMS = async () => {
    try {
      setSyncing(true);
      toast.loading("Syncing LMS...", { id: "syncToast" });
      await api("/sync", { method: "POST" });
    } catch {
      setSyncing(false);
      toast.dismiss("syncToast");
      toast.error("Failed to start sync");
    }
  };

  /* ---------------- LOGOUT ---------------- */
  const logout = () => {
    localStorage.removeItem("token");
    navigate("/");
  };

  /* ---------------- STATS ---------------- */
  const stats = useMemo(() => {
    const now = new Date();
    let dueSoon = 0;
    let overdue = 0;

    assignments.forEach(a => {
      if (a.submitted || !a.deadline) return;
      const d = new Date(a.deadline);
      const diff = d - now;

      if (diff < 0) overdue++;
      else if (diff <= 48 * 60 * 60 * 1000) dueSoon++;
    });

    return {
      total: assignments.length,
      dueSoon,
      overdue,
    };
  }, [assignments]);

  /* ---------------- FILTER + SORT ---------------- */
  const filteredAssignments = useMemo(() => {
    const now = new Date();

    return assignments
      .filter(a => {
        if (filter === "overdue")
          return !a.submitted && new Date(a.deadline) < now;

        if (filter === "due")
          return (
            !a.submitted &&
            new Date(a.deadline) > now &&
            new Date(a.deadline) - now <= 48 * 60 * 60 * 1000
          );

        return true;
      })
      .filter(a => {
        if (sortCourse !== "all") return a.course === sortCourse;
        return true;
      })
      .filter(a => {
        const text = `${a.course} ${a.title} ${a.no}`.toLowerCase();
        return text.includes(search.toLowerCase());
      })
      .sort((a, b) => {
        const now = new Date();

        const score = x => {
          const d = x.deadline ? new Date(x.deadline) : null;
          if (x.submitted) return 3;
          if (d && d < now) return 0;
          if (d && d - now <= 48 * 60 * 60 * 1000) return 1;
          return 2;
        };

        return score(a) - score(b);
      });
  }, [assignments, filter, search, sortCourse]);

  const courses = [...new Set(assignments.map(a => a.course))];

  return (
    <div className="page">
      <div className="dashboard">
        <header className="topbar">
          <h2>Bahria LMS Tracker</h2>
          <button className="logout" onClick={logout}>Logout</button>
        </header>

        <StatsBar stats={stats} onFilter={setFilter} active={filter} />

        {/* ---------------- TABS ---------------- */}
        <div className="tabs">
          <button
            className={activeTab === "assignments" ? "tab active" : "tab"}
            onClick={() => setActiveTab("assignments")}
          >
            Assignments
          </button>

          <button
            className={activeTab === "attendance" ? "tab active" : "tab"}
            onClick={() => {
              setActiveTab("attendance");
              if (attendance.length === 0) loadAttendance();
            }}
          >
            Attendance
          </button>
        </div>

        {/* ================= ASSIGNMENTS TAB ================= */}
        {activeTab === "assignments" && (
          <>
            <div className="actions">
              <input
                className="search"
                placeholder="Search assignment or course..."
                value={search}
                onChange={e => setSearch(e.target.value)}
              />

              <select
                className="select"
                value={sortCourse}
                onChange={e => setSortCourse(e.target.value)}
              >
                <option value="all">All Courses</option>
                {courses.map(c => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>

              <button onClick={syncLMS} disabled={syncing}>
                {syncing ? "Syncing..." : "Sync LMS"}
              </button>
            </div>

            {loading && <SkeletonAssignment />}
            {error && <div className="error">{error}</div>}

            {!loading && filteredAssignments.length === 0 && (
              <div className="empty">
                {syncing ? "Syncing LMS..." : "No assignments found"}
              </div>
            )}

            <div className="cards">
              {!loading &&
                filteredAssignments.map(a => (
                  <AssignmentCard key={`${a.course}-${a.no}`} data={a} />
                ))}
            </div>
          </>
        )}

        {/* ================= ATTENDANCE TAB ================= */}
        {activeTab === "attendance" && (
          <div className="attendance-section">

            {attendanceLoading && <p>Loading attendance...</p>}

            {!attendanceLoading && attendance.length === 0 && (
              <div className="empty">
                {syncing ? "Syncing LMS..." : "No attendance data found"}
              </div>
            )}

            {!attendanceLoading && attendance.length > 0 && (
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
                  {attendance.map(a => (
                    <tr key={a.course}>
                      <td>{a.course}</td>
                      <td>{a.present}</td>
                      <td>{a.total}</td>
                      <td>
                        <span
                          className={
                            a.percentage >= 80
                              ? "att-good"
                              : a.percentage >= 60
                              ? "att-mid"
                              : "att-bad"
                          }
                        >
                          {a.percentage}%
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/* ---------------- ASSIGNMENT CARD ---------------- */
function AssignmentCard({ data }) {
  const now = new Date();
  const deadline = data.deadline ? new Date(data.deadline) : null;

  let status = "pending";
  if (data.submitted) status = "done";
  else if (deadline && deadline < now) status = "overdue";
  else if (deadline && deadline - now <= 48 * 60 * 60 * 1000) status = "due";

  return (
    <div className={`card glow-${status}`}>
      <h3>{data.course}</h3>
      <p>{data.title}</p>

      <span className={`badge ${status}`}>
        {status === "done" && "✅ Submitted"}
        {status === "overdue" && "❌ Overdue"}
        {status === "due" && "⚠ Due Soon"}
        {status === "pending" && "⏳ Pending"}
      </span>

      <span className="deadline">
        ⏰ {deadline ? deadline.toLocaleString() : "No deadline"}
      </span>
    </div>
  );
}
