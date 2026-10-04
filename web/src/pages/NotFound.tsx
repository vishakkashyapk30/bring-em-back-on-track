import { Link } from "react-router-dom";

import { SectionTag } from "@/components/SectionTag";
import { EmptyState } from "@/components/States";

/** 404: the same page header as every other page, then a plain way back. */
export default function NotFound() {
  return (
    <>
      <SectionTag as="h1" subtitle="The link may be old, or the page may have moved.">Page not found</SectionTag>
      <EmptyState title="We can't find that page" detail="Check the address, or go back to the home page."
        action={<Link to="/" className="mt-2 inline-flex h-10 items-center rounded-[var(--radius-md)] border border-grey-300 bg-white px-4 font-medium text-ink no-underline hover:border-ink/40 hover:bg-grey-100 hover:no-underline">Back to the home page</Link>} />
    </>
  );
}
