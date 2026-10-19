// Pure admission comparison. Observations and policy provenance are external.
using System;

internal static class Ea4eProtectedIssuerAdmissionCandidate
{
    internal static string Evaluate(
        Ea4eProtectedIssuerPolicyCandidate.Policy policy,
        Ea4eProtectedIssuerToken.Observation token,
        Ea4eProtectedIssuerImage.Observation image,
        string observedStoreId, int observedStoreEpoch,
        string observedSourceCommit, string observedAuthorityId,
        long now, long expiresAt)
    {
        if (policy == null) return "POLICY_MISSING";
        if (Ea4eProtectedIssuerToken.Evaluate(
                policy.Text("operator_sid"), token) != "MATCH_ELEVATED_TOKEN")
            return "OPERATOR_TOKEN_DENIED";
        if (Ea4eProtectedIssuerImage.Evaluate(
                policy.Text("issuer_path"), policy.Text("issuer_sha256"), image)
            != "MATCH_IMAGE_BYTES")
            return "ISSUER_DISK_IMAGE_DENIED";
        if (!String.Equals(observedStoreId, policy.Text("store_id"),
                           StringComparison.Ordinal)
            || observedStoreEpoch != policy.Number("store_epoch"))
            return "STORE_IDENTITY_DENIED";
        if (!String.Equals(observedSourceCommit,
                           policy.Text("governing_commit"), StringComparison.Ordinal)
            || !String.Equals(observedAuthorityId,
                              policy.Text("authority_id"), StringComparison.Ordinal))
            return "SOURCE_AUTHORITY_DENIED";
        if (now < 1 || expiresAt <= now
            || expiresAt - now > policy.Number("max_ttl_seconds"))
            return "TIME_WINDOW_DENIED";
        return "CANDIDATE_MATCH_NOT_AUTHORITY";
    }
}
