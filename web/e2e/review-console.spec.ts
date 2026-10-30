import { expect, test } from "@playwright/test";

test("reviews missing-field, stale-verification, and duplicate candidate cases", async ({ page }, testInfo) => {
  const missingCase = testInfo.project.name === "mobile"
    ? { provider: "Robert Lane MD", field: "specialty" }
    : { provider: "Jordan Ellis DO", field: "phone" };

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Decide with evidence, not automation." })).toBeVisible();
  await expect(page.getByText(/bounded review data/i)).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("queue-overview.png"), fullPage: true });

  await page.getByRole("button", { name: /missing required field/i }).click();
  await page.getByRole("row", { name: new RegExp(missingCase.provider) }).click();
  await expect(page.getByText(new RegExp(`${missingCase.field} is required`))).toBeVisible();
  await expect(page.getByRole("region", { name: "Normalized record comparison" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("missing-field-evidence.png"), fullPage: true });
  await page.getByLabel("Action").selectOption("assign");
  await page.getByLabel("Assignee").fill("Avery");
  const decisionReason = `Route missing ${missingCase.field} for source confirmation`;
  await page.getByLabel(/Reason/).fill(decisionReason);
  const saveEvent = page.getByRole("button", { name: "Save event" });
  await page.locator(".action-panel").scrollIntoViewIfNeeded();
  await saveEvent.click();
  await expect(page.locator("aside .status-assigned")).toBeVisible();
  await expect(page.locator("aside .history")).toContainText(decisionReason);
  await page.screenshot({ path: testInfo.outputPath("recorded-decision-history.png"), fullPage: true });

  await page.getByRole("button", { name: /stale verification/i }).click();
  await page.getByRole("row", { name: /Anita Shah NP/i }).click();
  await expect(page.locator("aside .rule-callout")).toContainText(/last verified/i);

  await page.getByRole("button", { name: /possible duplicate provider location/i }).click();
  await page.getByRole("row", { name: /Keisha Thompson MD/i }).click();
  await expect(page.getByText(/candidate only — no automatic merge/i)).toBeVisible();
  await expect(page.getByRole("region", { name: "Normalized record comparison" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("duplicate-comparison.png"), fullPage: true });
});
