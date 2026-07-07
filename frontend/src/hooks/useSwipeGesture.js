import { useEffect, useLayoutEffect, useRef } from 'react';

export function useSwipeGesture(ref, onSwipe, { threshold = 50, maxVerticalDrift = 75, direction = 'right' } = {}) {
  const callbackRef = useRef(onSwipe);
  useLayoutEffect(() => {
    callbackRef.current = onSwipe;
  });

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    let startX = 0;
    let startY = 0;

    function onTouchStart(e) {
      startX = e.touches[0].clientX;
      startY = e.touches[0].clientY;
    }

    function onTouchEnd(e) {
      const dx = e.changedTouches[0].clientX - startX;
      const dy = Math.abs(e.changedTouches[0].clientY - startY);
      const passed = direction === 'left' ? dx <= -threshold : dx >= threshold;
      if (passed && dy <= maxVerticalDrift) {
        callbackRef.current();
      }
    }

    el.addEventListener('touchstart', onTouchStart);
    el.addEventListener('touchend', onTouchEnd);

    return () => {
      el.removeEventListener('touchstart', onTouchStart);
      el.removeEventListener('touchend', onTouchEnd);
    };
  }, [ref, threshold, maxVerticalDrift, direction]);
}
