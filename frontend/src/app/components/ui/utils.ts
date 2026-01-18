import { clsx, type ClassValue } from "clsx/clsx.d.mts";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}
