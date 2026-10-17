import { clsx, type ClassValue } from "clsx";

/** Join conditional class names. */
export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}
