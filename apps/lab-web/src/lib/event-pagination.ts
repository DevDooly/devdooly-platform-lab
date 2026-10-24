import type { Outcome } from './api.ts';

export const EVENT_PAGE_SIZES = [25, 50, 100] as const;
export type EventPageSize = typeof EVENT_PAGE_SIZES[number];

export interface EventPage {
  rows: Outcome[];
  index: number;
  totalPages: number;
  total: number;
  /** One-based positions within the filtered result, not event sequence values. */
  start: number;
  end: number;
}

/** Page already-filtered rows without changing their order, identity or reported fields. */
export function eventPage(outcomes: readonly Outcome[], requestedPage: number, pageSize: EventPageSize): EventPage {
  const total = outcomes.length;
  const totalPages = Math.ceil(total / pageSize);
  const requestedIndex = Number.isInteger(requestedPage) ? requestedPage : 0;
  const index = totalPages === 0 ? 0 : Math.max(0, Math.min(requestedIndex, totalPages - 1));
  const offset = index * pageSize;
  return {
    rows: outcomes.slice(offset, offset + pageSize),
    index, totalPages, total,
    start: total === 0 ? 0 : offset + 1,
    end: Math.min(offset + pageSize, total),
  };
}

/** Locate a selected event by sequence in the same filtered order used by the table. */
export function eventPageForSequence(outcomes: readonly Outcome[], sequence: number | null, pageSize: EventPageSize): number | null {
  if (sequence === null) return null;
  const position = outcomes.findIndex(outcome => outcome.sequence === sequence);
  return position === -1 ? null : Math.floor(position / pageSize);
}
