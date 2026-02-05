import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"
import axios from "axios"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Extract a user-friendly error message from an unknown error.
 * Handles Axios errors, standard Error objects, and unknown types.
 */
export function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    // Handle Axios errors - check for server response message first
    const serverMessage = error.response?.data?.message || error.response?.data?.detail;
    if (typeof serverMessage === 'string') {
      return serverMessage;
    }
    // Fall back to Axios error message
    return error.message || 'A network error occurred';
  }

  if (error instanceof Error) {
    return error.message;
  }

  if (typeof error === 'string') {
    return error;
  }

  return 'An unknown error occurred';
}
