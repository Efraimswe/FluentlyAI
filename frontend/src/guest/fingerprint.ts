/** Stable-ish guest id: sha256(UA + screen + tz + lang + WebGL renderer + canvas hash), cached in a cookie + localStorage. */

const COOKIE_NAME = "cc_fp";
const STORAGE_KEY = "cc_fp";

function getCookie(name: string): string | null {
  try {
    const match = document.cookie.match(
      new RegExp("(?:^|; )" + name.replace(/([.$?*|{}()[\]\\/+^])/g, "\\$1") + "=([^;]*)"),
    );
    return match ? decodeURIComponent(match[1]) : null;
  } catch {
    return null;
  }
}

function setCookie(name: string, value: string): void {
  try {
    const secure = location.protocol === "https:" ? "; Secure" : "";
    document.cookie = `${name}=${encodeURIComponent(value)}; Max-Age=31536000; Path=/; SameSite=Lax${secure}`;
  } catch {
    // ignore
  }
}

function getUserAgent(): string {
  try {
    return navigator.userAgent;
  } catch {
    return "noua";
  }
}

function getScreenInfo(): string {
  try {
    return `${screen.width}x${screen.height}x${screen.colorDepth}`;
  } catch {
    return "noscreen";
  }
}

function getTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone;
  } catch {
    return "notz";
  }
}

function getLanguage(): string {
  try {
    return navigator.language;
  } catch {
    return "nolang";
  }
}

function getWebglRenderer(): string {
  try {
    const canvas = document.createElement("canvas");
    const gl = canvas.getContext("webgl") as WebGLRenderingContext | null;
    if (!gl) return "nogl";
    const ext = gl.getExtension("WEBGL_debug_renderer_info");
    if (!ext) return "nogl";
    const renderer = gl.getParameter(ext.UNMASKED_RENDERER_WEBGL);
    return typeof renderer === "string" ? renderer : "nogl";
  } catch {
    return "nogl";
  }
}

function getCanvasHash(): string {
  try {
    const canvas = document.createElement("canvas");
    canvas.width = 200;
    canvas.height = 50;
    const ctx = canvas.getContext("2d");
    if (!ctx) return "nocanvas";
    ctx.textBaseline = "top";
    ctx.font = "16px Arial";
    ctx.fillStyle = "#f60";
    ctx.fillRect(10, 10, 60, 20);
    ctx.fillStyle = "#069";
    ctx.fillText("fingerprint 😀", 2, 2);
    return canvas.toDataURL();
  } catch {
    return "nocanvas";
  }
}

function fnv1aHex(input: string): string {
  let hash = 0x811c9dc5;
  for (let i = 0; i < input.length; i++) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

async function hashParts(parts: string[]): Promise<string> {
  const joined = parts.join("|");
  try {
    if (crypto.subtle) {
      const data = new TextEncoder().encode(joined);
      const digest = await crypto.subtle.digest("SHA-256", data);
      return Array.from(new Uint8Array(digest))
        .map((b) => b.toString(16).padStart(2, "0"))
        .join("");
    }
  } catch {
    // fall through to FNV-1a fallback
  }
  return fnv1aHex(joined);
}

export async function getFingerprint(): Promise<string> {
  const cached = getCookie(COOKIE_NAME) ?? readLocalStorage();
  if (cached) return cached;

  const parts = [
    getUserAgent(),
    getScreenInfo(),
    getTimeZone(),
    getLanguage(),
    getWebglRenderer(),
    getCanvasHash(),
  ];
  const fingerprint = await hashParts(parts);

  setCookie(COOKIE_NAME, fingerprint);
  writeLocalStorage(fingerprint);

  return fingerprint;
}

function readLocalStorage(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeLocalStorage(value: string): void {
  try {
    localStorage.setItem(STORAGE_KEY, value);
  } catch {
    // ignore
  }
}

export function clearFingerprint(): void {
  try {
    document.cookie = `${COOKIE_NAME}=; Max-Age=0; Path=/; SameSite=Lax`;
  } catch {
    // ignore
  }
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}
