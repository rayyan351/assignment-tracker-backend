const API = "http://127.0.0.1:10000/api";

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
