// @vitest-environment jsdom
import React, { StrictMode } from "react";
import { act, cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { IrisIntroOverlay } from "../src/components/iris-intro/IrisIntroOverlay";

describe("IrisIntroOverlay", () => {
  const originalMatchMedia = window.matchMedia;

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    window.matchMedia = originalMatchMedia;
  });

  it("dispara onExitStart e onFinished sob React StrictMode com prefers-reduced-motion ativo", () => {
    vi.useFakeTimers();
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query === "(prefers-reduced-motion: reduce)",
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));

    const onExitStart = vi.fn();
    const onFinished = vi.fn();

    render(
      <StrictMode>
        <IrisIntroOverlay onExitStart={onExitStart} onFinished={onFinished} />
      </StrictMode>
    );

    act(() => {
      vi.advanceTimersByTime(650);
    });
    expect(onExitStart).toHaveBeenCalledTimes(1);
    expect(onFinished).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(350);
    });
    expect(onFinished).toHaveBeenCalledTimes(1);
  });
});
