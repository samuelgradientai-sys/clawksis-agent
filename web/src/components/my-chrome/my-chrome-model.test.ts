import { describe, expect, it } from "vitest";
import type { MyChromeStatus } from "@/lib/api-my-chrome";
import { myChromeCopy } from "./copy";
import { hostOf, myChromeState, statusView, tabBadges } from "./my-chrome-model";

const base: MyChromeStatus = {
  enabled: true,
  confirm_payments: false,
  paired: true,
  paired_at: 1,
  connected: false,
  active: false,
  connected_at: null,
  browser: null,
  extension_version: null,
  tabs: [],
};

describe("myChromeState", () => {
  it("off wins over everything: a disabled feature refuses the extension", () => {
    expect(myChromeState({ ...base, enabled: false, connected: true })).toBe("off");
  });

  it("tells a paired-but-absent Chrome from a never-paired one", () => {
    expect(myChromeState(base)).toBe("waiting");
    expect(myChromeState({ ...base, paired: false })).toBe("unpaired");
    expect(myChromeState({ ...base, connected: true })).toBe("connected");
  });
});

describe("statusView", () => {
  it("names the connected browser", () => {
    const view = statusView({ ...base, connected: true, browser: "Chrome/141.0", connected_at: 0 }, myChromeCopy);
    expect(view.label).toBe(myChromeCopy.statusConnected);
    expect(view.detail).toContain("Chrome/141.0");
  });
});

describe("tab labels", () => {
  it("shows the host, and the badges a tab earns", () => {
    expect(hostOf("https://vuelaya.example/checkout?x=1")).toBe("vuelaya.example");
    expect(hostOf("not a url")).toBe("not a url");
    const tab = { id: "T", title: "", url: "", active: true, agent: true, attached: false };
    expect(tabBadges(tab, myChromeCopy)).toEqual([myChromeCopy.tabAgent, myChromeCopy.tabActive]);
  });
});
