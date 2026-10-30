import { expect, test } from "@playwright/test";

const paths = {
  wide: {
    golden: { listing: "PAYER-00002", field: "state", proposal: "GA", observed: "ga" },
    reopen: { listing: "PAYER-00003", field: "status", proposal: "hold", observed: "pending" },
  },
  mobile: {
    golden: { listing: "PAYER-00004", field: "accepting new patients", proposal: "no", observed: "no" },
    reopen: { listing: "PAYER-00001", field: "phone", proposal: "615-555-0199", observed: "615-555-0188" },
  },
} as const;

async function enterRemediation(page: import("@playwright/test").Page, listing: string, field: string) {
  await page.goto("/");
  await page.getByRole("button", { name: /open remediation loop/i }).click();
  await expect(page.getByRole("heading", { name: "Follow the evidence through verification." })).toBeVisible();
  await page.getByRole("row", { name: new RegExp(`Open remediation case ${listing}, ${field}`, "i") }).click();
  await expect(page.getByText("Immutable Phase 1 snapshot")).toBeVisible();
}

async function record(page: import("@playwright/test").Page, action: string, reason: string, extras: Record<string, string> = {}) {
  await page.getByRole("button", { name: action, exact: true }).click();
  await page.getByLabel("Remediation actor").fill("Morgan Reviewer");
  await page.getByLabel("Remediation reason").fill(reason);
  for (const [label, value] of Object.entries(extras)) await page.getByLabel(label).fill(value);
  await page.getByRole("button", { name: new RegExp(`Record ${action}`, "i") }).click();
  await expect(page.getByText(/Event recorded. The queue, case, and audit history were refreshed/i)).toBeVisible();
}

test("records the payer remediation golden path with immutable evidence", async ({ page }, testInfo) => {
  const path = paths[testInfo.project.name as keyof typeof paths].golden;
  await enterRemediation(page, path.listing, path.field);
  await expect(page.getByText("Comparison reference, not certified truth.")).toBeVisible();
  await record(page, "triage", "Begin source-backed human review");
  await record(page, "approve", "Approve the correction after reviewing the snapshot", { "Proposed correction": path.proposal });
  await expect(page.locator(".value-proposal strong")).toHaveText(path.proposal);
  await record(page, "submit", "Record payer portal submission", { "Submission reference": `TICKET-${testInfo.project.name}-GOLDEN` });
  await record(page, "verify", "Observed the approved value in the payer directory", { "Observed payer value": path.observed, "Verification evidence note": "Observed in the synthetic payer portal during verification." });
  await expect(page.locator(".remediation-detail .status-verified")).toBeVisible();
  await expect(page.locator(".remediation-history li").filter({ hasText: "Observed payer value:" }).last()).toContainText(path.observed);
  await page.screenshot({ path: testInfo.outputPath("remediation-verified.png"), fullPage: true });
});

test("reopens a remediation case when verification does not match the approved proposal", async ({ page }, testInfo) => {
  const path = paths[testInfo.project.name as keyof typeof paths].reopen;
  await enterRemediation(page, path.listing, path.field);
  await record(page, "triage", "Begin review of the payer discrepancy");
  await record(page, "approve", "Approve a value that must be verified", { "Proposed correction": path.proposal });
  await record(page, "submit", "Record payer submission reference", { "Submission reference": `TICKET-${testInfo.project.name}-REOPEN` });
  await record(page, "verify", "Observed payer value does not equal the approved proposal", { "Observed payer value": path.observed, "Verification evidence note": "The payer directory still shows a different value." });
  await expect(page.getByText("Verification failed — reopened")).toBeVisible();
  await expect(page.locator(".remediation-detail .status-reopened")).toBeVisible();
  await expect(page.locator(".remediation-history li").filter({ hasText: "Observed payer value:" }).last()).toContainText(path.observed);
  await page.screenshot({ path: testInfo.outputPath("remediation-reopened.png"), fullPage: true });
});
