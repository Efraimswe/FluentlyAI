import { authHeaders } from '../auth/supabase';

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) || '';

declare global {
  interface Window {
    createLemonSqueezy?: () => void;
    LemonSqueezy?: {
      Setup(config: { eventHandler(event: { event: string }): void }): void;
      Url: {
        Open(url: string): void;
      };
    };
  }
}

let lemonScriptPromise: Promise<void> | null = null;

function loadLemonScript(): Promise<void> {
  if (!lemonScriptPromise) {
    lemonScriptPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = 'https://assets.lemonsqueezy.com/lemon.js';
      script.defer = true;
      script.onload = () => resolve();
      script.onerror = () => reject(new Error('lemon.js failed to load'));
      document.head.appendChild(script);
    });
  }
  return lemonScriptPromise;
}

function withTimeout(promise: Promise<void>, ms: number): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error('lemon.js timed out')), ms);
    promise.then(
      () => {
        window.clearTimeout(timer);
        resolve();
      },
      (err: unknown) => {
        window.clearTimeout(timer);
        reject(err instanceof Error ? err : new Error('lemon.js failed'));
      },
    );
  });
}

export async function openCheckout(): Promise<void> {
  const headers = await authHeaders();
  const res = await fetch(`${API_BASE}/api/checkout`, {
    method: 'POST',
    headers,
  });
  if (!res.ok) {
    throw new Error(`checkout failed: ${res.status}`);
  }
  const data = (await res.json()) as { url: string };
  const url = data.url;

  try {
    await withTimeout(loadLemonScript(), 5000);
    window.createLemonSqueezy?.();
    window.LemonSqueezy?.Setup({
      eventHandler: (e) => {
        if (e.event === 'Checkout.Success') {
          window.dispatchEvent(new CustomEvent('cc:checkout-success'));
        }
      },
    });
    window.LemonSqueezy?.Url.Open(url);
  } catch {
    window.location.href = url;
  }
}
