import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}

export function stripMarkdown(text) {
  if (!text) return '';
  return text
    .replace(/!\[.*?\]\(.*?\)/g, '')          // images
    .replace(/\[([^\]]+)\]\(.*?\)/g, '$1')    // links → label
    .replace(/^#{1,6}\s+/gm, '')              // headings
    .replace(/(\*\*|__)(.*?)\1/g, '$2')       // bold
    .replace(/(\*|_)(.*?)\1/g, '$2')          // italic
    .replace(/`{3}[\s\S]*?`{3}/g, '')         // fenced code blocks
    .replace(/`([^`]+)`/g, '$1')              // inline code
    .replace(/^>\s+/gm, '')                   // blockquotes
    .replace(/^[-*+]\s+/gm, '')               // unordered lists
    .replace(/^\d+\.\s+/gm, '')               // ordered lists
    .replace(/^[-*_]{3,}\s*$/gm, '')          // horizontal rules
    .replace(/\n+/g, ' ')                     // collapse newlines
    .trim();
}
