import { renderHook } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useSwipeGesture } from './useSwipeGesture';

function makeRef(el) {
  return { current: el };
}

function fireTouchStart(el, x, y) {
  const event = new Event('touchstart');
  Object.defineProperty(event, 'touches', { value: [{ clientX: x, clientY: y }] });
  el.dispatchEvent(event);
}

function fireTouchEnd(el, x, y) {
  const event = new Event('touchend');
  Object.defineProperty(event, 'changedTouches', { value: [{ clientX: x, clientY: y }] });
  el.dispatchEvent(event);
}

function fireSwipe(el, startX, startY, endX, endY) {
  fireTouchStart(el, startX, startY);
  fireTouchEnd(el, endX, endY);
}

describe('useSwipeGesture', () => {
  let el;
  beforeEach(() => {
    el = document.createElement('div');
  });

  it('fires callback on rightward swipe above threshold', () => {
    const cb = vi.fn();
    renderHook(() => useSwipeGesture(makeRef(el), cb));
    fireSwipe(el, 0, 0, 60, 0);
    expect(cb).toHaveBeenCalledOnce();
  });

  it('does not fire below threshold', () => {
    const cb = vi.fn();
    renderHook(() => useSwipeGesture(makeRef(el), cb));
    fireSwipe(el, 0, 0, 40, 0);
    expect(cb).not.toHaveBeenCalled();
  });

  it('does not fire on leftward swipe', () => {
    const cb = vi.fn();
    renderHook(() => useSwipeGesture(makeRef(el), cb));
    fireSwipe(el, 100, 0, 30, 0);
    expect(cb).not.toHaveBeenCalled();
  });

  it('does not fire when vertical drift exceeds tolerance', () => {
    const cb = vi.fn();
    renderHook(() => useSwipeGesture(makeRef(el), cb));
    // deltaX=60 (above 50px threshold) but deltaY=80 (above 75px tolerance)
    fireSwipe(el, 0, 0, 60, 80);
    expect(cb).not.toHaveBeenCalled();
  });

  it('fires exactly at the threshold boundary', () => {
    const cb = vi.fn();
    renderHook(() => useSwipeGesture(makeRef(el), cb));
    fireSwipe(el, 0, 0, 50, 0);
    expect(cb).toHaveBeenCalledOnce();
  });

  it('fires when vertical drift is exactly at the tolerance boundary', () => {
    const cb = vi.fn();
    renderHook(() => useSwipeGesture(makeRef(el), cb));
    fireSwipe(el, 0, 0, 60, 75);
    expect(cb).toHaveBeenCalledOnce();
  });

  // ── direction: 'left' ────────────────────────────────────────────────────

  it('fires callback on leftward swipe when direction is left', () => {
    const cb = vi.fn();
    renderHook(() => useSwipeGesture(makeRef(el), cb, { direction: 'left' }));
    fireSwipe(el, 100, 0, 30, 0);
    expect(cb).toHaveBeenCalledOnce();
  });

  it('does not fire on rightward swipe when direction is left', () => {
    const cb = vi.fn();
    renderHook(() => useSwipeGesture(makeRef(el), cb, { direction: 'left' }));
    fireSwipe(el, 0, 0, 60, 0);
    expect(cb).not.toHaveBeenCalled();
  });

  it('does not fire leftward below threshold when direction is left', () => {
    const cb = vi.fn();
    renderHook(() => useSwipeGesture(makeRef(el), cb, { direction: 'left' }));
    fireSwipe(el, 100, 0, 60, 0);
    expect(cb).not.toHaveBeenCalled();
  });
});
