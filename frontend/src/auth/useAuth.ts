import { useEffect, useState } from 'react';
import { supabase, signInWithGoogle, signInWithEmail, signOut } from './supabase';

export interface AuthUser {
  id: string;
  email: string | null;
}

export function useAuth(): {
  user: AuthUser | null;
  loading: boolean;
  signInWithGoogle(): Promise<void>;
  signInWithEmail(email: string): Promise<{ error: string | null }>;
  signOut(): Promise<void>;
} {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;

    supabase.auth.getSession().then(({ data }) => {
      if (!active) return;
      const session = data.session;
      setUser(session ? { id: session.user.id, email: session.user.email ?? null } : null);
      setLoading(false);
    });

    const { data: subscription } = supabase.auth.onAuthStateChange((_event, session) => {
      setUser(session ? { id: session.user.id, email: session.user.email ?? null } : null);
    });

    return () => {
      active = false;
      subscription.subscription.unsubscribe();
    };
  }, []);

  return { user, loading, signInWithGoogle, signInWithEmail, signOut };
}
