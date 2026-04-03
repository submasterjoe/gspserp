/**
 * Greeting by time of day; initials from name; Unsplash avatar helper
 */
function getGreeting(name) {
  const h = new Date().getHours();
  let part = "Hello";
  if (h < 12) part = "Good morning";
  else if (h < 18) part = "Good afternoon";
  else part = "Good evening";
  const n = name && name.trim() ? name.trim() : "there";
  return `${part}, ${n}`;
}

function initialsFromName(name) {
  if (!name || !name.trim()) return "SP";
  const parts = name.trim().split(/\s+/).slice(0, 2);
  return parts.map((p) => p[0].toUpperCase()).join("") || "SP";
}

/** Build a stable Unsplash URL (source.unsplash.com redirects; user can replace with API) */
function unsplashAvatarUrl(seed, size = 128) {
  const s = encodeURIComponent(seed || "professional");
  return `https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=${size}&h=${size}&fit=crop&auto=format&q=70`;
}

globalThis.GspsProfile = {
  getGreeting,
  initialsFromName,
  unsplashAvatarUrl,
};
