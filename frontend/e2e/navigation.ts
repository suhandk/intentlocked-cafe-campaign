import { expect, type Page } from "@playwright/test";
export async function stage(page:Page, id:string) {
  const ids=["speak-type","facts-lock","brand-strategy","campaign-matrix","prediction","guardian","ledger-changes","approve-export"];
  const button=page.getByRole("navigation",{name:"Campaign workflow"}).locator(".stepper-item").nth(ids.indexOf(id));
  await expect(button).not.toHaveAttribute("aria-disabled","true");
  await button.click();
  await expect(page.locator(`.stage-view[data-stage="${id}"]`).first()).toBeVisible();
  await expect(page.locator(`.stage-view[data-stage="${id}"]`).first()).toHaveCSS("opacity","1");
}
export async function trace(page:Page) {await page.getByRole("button",{name:"Open trace drawer",exact:true}).click();await expect(page.getByRole("dialog",{name:"Trace & saved work"})).toBeVisible();}
export async function closeTrace(page:Page) {await page.getByRole("dialog",{name:"Trace & saved work"}).getByRole("button",{name:"Close dialog"}).click();}
