const API = "https://assignment-tracker-backend-gz1c.onrender.com/api";

export async function api(path, options = {}) {
  const token = localStorage.getItem("token");

  const res = await fetch(`${API}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(token && { Authorization: token })
    },
    ...options
  });

  const data = await res.json();
  if (!res.ok) throw data;
  return data;
}
