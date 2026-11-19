import { redirect } from "next/navigation";

export default async function CompanyRoot({
  params,
}: {
  params: Promise<{ companyId: string }>;
}) {
  const { companyId } = await params;
  redirect(`/${companyId}/graph`);
}
