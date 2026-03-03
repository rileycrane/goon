const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

function getPassword(): string {
  if (typeof window === "undefined") return "";
  return sessionStorage.getItem("admin_password") || "";
}

export async function adminFetch(path: string): Promise<any> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "X-Admin-Password": getPassword() },
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

export async function adminPost(path: string, body: any = {}): Promise<any> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Admin-Password": getPassword(),
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}
