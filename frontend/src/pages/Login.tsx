import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { apiClient } from '@/api/client';
import { getErrorMessage } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { AlertCircle, Loader2, UserPlus } from 'lucide-react';

export const Login: React.FC = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isFirstRun, setIsFirstRun] = useState<boolean | null>(null);
  const [isCheckingFirstRun, setIsCheckingFirstRun] = useState(true);
  const { login, setUser } = useAuth();
  const navigate = useNavigate();
  const isSubmittingRef = useRef(false);

  useEffect(() => {
    const checkInitialState = async () => {
      try {
        const result = await apiClient.checkFirstRun();
        setIsFirstRun(result.first_run);
      } catch (err) {
        console.error('Failed to check initial state:', err);
        setIsFirstRun(false);
      } finally {
        setIsCheckingFirstRun(false);
      }
    };
    checkInitialState();
  }, []);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      await login({ username, password });
      navigate('/');
    } catch (err) {
      setError('Invalid username or password');
    } finally {
      setIsLoading(false);
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isSubmittingRef.current) return;
    isSubmittingRef.current = true;
    setError('');

    if (password !== confirmPassword) {
      setError('Passwords do not match');
      isSubmittingRef.current = false;
      return;
    }

    if (password.length < 6) {
      setError('Password must be at least 6 characters');
      isSubmittingRef.current = false;
      return;
    }

    if (username.length < 3) {
      setError('Username must be at least 3 characters');
      isSubmittingRef.current = false;
      return;
    }

    setIsLoading(true);

    try {
      const result = await apiClient.register(username, password);
      setUser(result.user);
      navigate('/');
    } catch (err) {
      const message = getErrorMessage(err);
      // If user was already created (double-submit or lost response),
      // try logging in with the same credentials
      if (message.toLowerCase().includes('already exist')) {
        try {
          await login({ username, password });
          navigate('/');
          return;
        } catch {
          setError('An account already exists. Please sign in with your credentials.');
          setIsFirstRun(false);
          return;
        }
      }
      setError(message);
    } finally {
      setIsLoading(false);
      isSubmittingRef.current = false;
    }
  };

  if (isCheckingFirstRun) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-1 text-center">
          <img src="/speedarr.svg" alt="Speedarr" className="h-16 w-16 mx-auto" />
          <CardTitle className="text-3xl font-bold">Speedarr</CardTitle>
          <CardDescription>
            {isFirstRun ? 'Create your admin account' : 'Bandwidth Management System'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isFirstRun && (
            <Alert className="mb-4">
              <UserPlus className="h-4 w-4" />
              <AlertDescription>
                Welcome to Speedarr! Create your admin account to get started.
              </AlertDescription>
            </Alert>
          )}

          {error && (
            <Alert variant="destructive" className="mb-4">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          <form onSubmit={isFirstRun ? handleRegister : handleLogin} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                type="text"
                placeholder={isFirstRun ? 'Choose a username' : 'Enter your username'}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                disabled={isLoading}
                required
                autoFocus
                autoComplete={isFirstRun ? 'off' : 'username'}
                maxLength={50}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                placeholder={isFirstRun ? 'Choose a password (min 6 chars)' : 'Enter your password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={isLoading}
                required
                autoComplete={isFirstRun ? 'new-password' : 'current-password'}
                maxLength={128}
              />
            </div>

            {isFirstRun && (
              <div className="space-y-2">
                <Label htmlFor="confirmPassword">Confirm Password</Label>
                <Input
                  id="confirmPassword"
                  type="password"
                  placeholder="Confirm your password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  disabled={isLoading}
                  required
                  autoComplete="new-password"
                  maxLength={128}
                />
              </div>
            )}

            <Button type="submit" className="w-full" disabled={isLoading}>
              {isLoading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  {isFirstRun ? 'Creating Account...' : 'Signing in...'}
                </>
              ) : (
                isFirstRun ? 'Create Account' : 'Sign In'
              )}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
};
