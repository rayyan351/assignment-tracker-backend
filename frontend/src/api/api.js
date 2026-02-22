const API = "https://assignment-tracker-backend-7xiw.onrender.com/api";

export async function api(path, options = {}) {
  const token = localStorage.getItem("token");

  const res = await fetch(`${API}${path}`, {
    mode: "cors",
    headers: {
      "Content-Type": "application/json",
      ...(token && { Authorization: `Bearer ${token}` })
    },
    ...options
  });

  const data = await res.json();
  if (!res.ok) throw data;
  return data;
}
