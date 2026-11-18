import datetime as dt
import json
import re
import unittest
from copy import deepcopy
from zoneinfo import ZoneInfo

from scripts import khs_bis_remote_rule as bis
from scripts import khs_trusted_policy_news_watch as host

NOW = dt.datetime(2026, 11, 18, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))
META = {
    "document_number": "2026-23529", "type": "Rule",
    "title": "Addressing Remote Access to Advanced Semiconductors",
    "agencies": [{"name": "Industry and Security Bureau"}],
    "publication_date": "2026-11-19", "filed_at": "2026-11-16T16:15:00-05:00",
    "html_url": bis.INSPECTION_URL,
    "raw_text_url": "https://www.federalregister.gov/public-inspection/raw_text/202/623/529.txt",
}
# Material passages from the public-domain 2026-23529 text; no live clock or IO.
BODY = r"""Bureau of Industry and Security. RIN 0694-AK50. Docket No. 261116-0005.
Addressing Remote Access to Advanced Semiconductors. ACTION: Interim final rule.
SUMMARY: In this interim final rule (IFR), the Department of Commerce is establishing new
rules to prevent certain foreign actors from leveraging advanced computing power based on U.S.
technology to threaten U.S. national security and foreign policy interests. First, this rule
establishes new restrictions which will apply for exports, reexports, or transfers (in-country) to
overseas data centers that remotely supply significant volumes of compute to companies
headquartered in Country Group D:5 or Macau. These restrictions will undermine the ability of
companies headquartered in countries of concern from using U.S. advanced Super Intelligence
(SI) semiconductors to train advanced SI models. Data centers, foreign foundries, and chip
exporters are required to perform robust due diligence on their customers, including any direct or
indirect ownership or control by persons in Country Group D:5 or Macau, as part of complying
with this new control. The license requirement will not apply to commercial recommender
systems, such as those used by online retailers or social media companies, as these functions do
not pose the same national security threat. Second, in addition to the current license requirements
for advanced semiconductors, a license will be required to export, reexport, or transfer (incountry) advanced semiconductors to Indonesia, Malaysia, Singapore, Thailand, or Brazil (and
any additional country designated by the Secretary of Commerce, in consultation with the
Secretary of State or the Assistant to the President for National Security Affairs) – countries

which present a higher-than-normal risk of diversion. The license requirement for these five
countries will not apply to semiconductors destined to companies headquartered in, or whose
ultimate parent company is headquartered in, the United States, provided certain reporting
requirements are met. Commerce will be actively monitoring for countries that tolerate evasion
of this IFR and will consider a range of consequences for such countries, such as import
restrictions, new license requirements on advanced semiconductor exports, downgrading the
country’s status in the U.S. export control regime, and Entity List designations and temporary
export prohibitions for foreign persons involved in such activities. Third, this IFR amends the
presumptions which front-end chips fabricators and chip packagers face when exporting
advanced-node logic chips. These amendments reduce the number of pathways to overcome the
presumptions for chip designers located in destinations which face a license requirement for SI
chips. This change gives the U.S. government critical oversight over companies headquartered in
certain countries that seek to leverage advanced semiconductor production capabilities in third
countries. Finally, the IFR formally rescinds the regulations implementing the Biden-era AI
Diffusion Rule. The AI Diffusion Rule has never been enforced. The regulatory changes in this
rule formalize the rescission of the AI Diffusion Rule, which the Department of Commerce
Bureau of Industry and Security (BIS) announced in May 2025.
DATES: Effective date: This rule is effective [INSERT DATE OF PUBLICATION IN THE FEDERAL REGISTER].
Comment due date: [INSERT DATE 60 DAYS AFTER PUBLICATION]. ADDRESSES: ...
§ 742.6 Regional stability.
(a) * * *
(6) * * *
(iii) * * *
(A) A license is required for items specified in ECCNs 3A001.z; 3A090 (except for 3A090.c);
3D001 (for “software” for commodities controlled by 3A001.z, 3A090 (except for 3A090.c));
3E001 (for “technology” for commodities controlled by 3A001.z, 3A090 (except for 3A090.c));
4A003.z; 4A004.z; 4A005.z; 4A090; 4D001 (for “software” for commodities controlled by
4A003.z, 4A004.z, and 4A005.z); 4D090 (for “software” for commodities controlled by 4A090);
4E001 (for “technology” for commodities controlled by 4A003.z, 4A004.z, 4A005.z, 4A090 or
“software” specified by 4D001 (for 4A003.z, 4A004.z, and 4A005.z), 4D090 (for “software” for
commodities controlled by 4A090)); 5A002.z; 5A004.z; 5A992.z; 5D002.z; 5D992.z; 5E002 (for
“technology” for commodities controlled by 5A002.z or 5A004.z or “software” specified by
5D002 (for 5A002.z or 5A004.z commodities)); or 5E992 (for “technology” for commodities
controlled by 5A992.z or “software” controlled by 5D992.z) for exports, reexports, and transfers
(in-country) to or within the destinations specified under paragraphs (a)(6)(iii)(A)(1)-(2).
(1) Indonesia, Malaysia, Singapore, Brazil, and Thailand.
Note 1 to paragraph (a)(6)(iii)(A)(1): The license requirements in this paragraph
(a)(6)(iii)(A)(1) do not apply to exports, reexports, and transfers (in-country) to an ultimate
consignee or end user headquartered in, or whose ultimate parent company is headquartered in,
the United States, provided the exporter, reexporter, or transferor follows the reporting
requirements in § 743.10 Reporting Requirements to Qualify for Exclusion from Certain
Regional Stability License Requirements.
(2) A destination in Country Groups D:1, D:4, or D:5 (excluding destinations also specified in
Country Groups A:5 or A:6) or the United Arab Emirates, except that a license is not required
when the ultimate consignee and all end users are approved entities in the United Arab Emirates

listed in supplement no. 8 to part 740 and specified as approved to receive the items covered by
this paragraph.
(B) [Reserved]
* * * * *
(iii) * * *
(A) * * *
(1) License review policy for paragraph (a)(6)(iii)(A)(1). Applications for exports, reexports, and
transfers (in-country) will be reviewed on a case-by-case basis to determine whether the
transaction is contrary to the national security or foreign policy interests of the United States, to
include the effectiveness of a destination’s export control regimes and coordination with
BIS on the enforcement of export controls.
(2) Policy for Country Groups D:1, D:4, D:5 and the United Arab Emirates. There is a case-bycase license review policy for license applications for exports of commodities with a TPP (as
defined in Technical Note 2 to 3A090.a and 3A090.b) less than 21,000, and a 'total DRAM
bandwidth' (as defined in the notes to paragraph (dd)(1) in supplement no. 2 to part 748) less
than 6,500 GB/s, when destined to end-users located in China or Macau, provided the applicant
provides the additional information described in supplement no. 2 to part 748 under paragraph
(dd). All other applications for exports, reexports, or transfers (in-country) to or within Country
Group D:5 and Macau or for an entity headquartered or with an ultimate parent headquartered in
Country Group D:5 or Macau will be reviewed under a presumption of denial. All other
applications to or within destinations specified in Country Groups D:1 and D:4 (excluding any
destinations also specified in Country Groups A:5 or A:6) and the United Arab Emirates will be
reviewed under a presumption of approval. If the license application meets the criteria of more
than one licensing policy, then this licensing policy and its requirements will be applied.
(B) [RESERVED]
* * * * *

PART 743

§ 743.10 Reporting requirements to qualify for exclusion from certain regional stability
license requirements.
(a) Scope. This section describes reporting which is required to qualify for an exclusion from the
Regional Stability license requirement under § 742.6(a)(6)(iii)(A)(1). Pursuant to Note 1 to
paragraph (a)(6)(iii)(A)(1), the license requirements in § 742.6(a)(6)(iii)(A)(1) do not apply to
exports, reexports, and transfers (in-country) to an ultimate consignee or end user headquartered
in, or whose ultimate parent company is headquartered in, the United States, provided the
exporter, reexporter, or transferor follows the reporting requirements of this section.
(b) Information to be included in the reports. The following information specified under
paragraph (b)(1) through (4) of this section must be included in each report to BIS.
(1) Information on each of the parties, as described in § 748.5, involved in the transaction as well
as the ultimate parent(s) of the ultimate consignee and end user, including:
(i) Name;
(ii) Physical address;
(iii) Mailing address (if different from physical address);
(iv) Phone number;
(v) Information in paragraphs (b)(1)(i) through (iv) for all parent company headquarters and
specifying which company is the ultimate parent; and
(vi) The role(s) each party is playing in the transaction (i.e., exporter, reexporter, transferor, enduser, ultimate consignee, or ultimate parent of the ultimate consignee or end-user).

(2) The ultimate destination of the commodities being exported, reexported or transferred (incountry) and any “end-users” of the commodity which are not the ultimate consignee.
(3) Information for each product being exported, exported from abroad, reexported, or
transferred (in-country) including:
(i) ECCN, including the item’s paragraph-level classification; e.g., 3A090.a;
(ii) Product name and SKU;
(iii) Total processing performance (TPP) of the product (see the Technical Notes to ECCN
3A090); and
(iv) Quantity of each product.
(4) Date of export, reexport, or transfer (in-country) for each commodity described in paragraph
(b)(3).
(c) Where to submit reports required under this section. Notifications to BIS under this section
must be submitted to BIS using the following URL:
https://www.bis.gov/ai/exclusionnotesubmission.
(d) Monthly reporting requirement. You must submit monthly reports regarding any
transactions subject to the provisions of this section. The report shall cover any exports,
reexports, or transfers (in-country) that qualify for an exclusion from the Regional Stability
license requirement pursuant to Note 1 to § 742.6(a)(6)(iii)(A)(1) on or after [INSERT DATE
OF PUBLICATION IN FEDERAL REGISTER]. Reports regarding any export, reexport, or
transfer (in-country) subject to the provisions of this section are due no later than the first
business day of the month following the transaction.
(e) Contacts. General information or questions about these reports can be directed to the Office
of National Security Controls, tel. (202) 482-0092, or email: EAR.Reports@bis.doc.gov.
PART 744

§ 744.24 Restrictions on exports, reexports, and transfers (in-country) of certain advanced
computing items for use in data centers for end-uses and destinations of concern.
(a) General prohibition—(1) Prohibition on exports, reexports, or transfers (in-country) for
certain advanced computing items for use in data centers for end uses of concern. In addition
to the license requirements set forth elsewhere in the EAR, you may not export, reexport, or
transfer (in-county) items specified in ECCNs 3A001.z; 3A090 (except for 3A090.c); 3D001 (for
“software” for commodities controlled by 3A001.z, 3A090 (except for 3A090.c)); 3E001 (for
“technology” for commodities controlled by 3A001.z, 3A090 (except for 3A090.c)); 4A003.z;
4A004.z; 4A005.z; 4A090; 4D001 (for “software” for commodities controlled by 4A003.z,
4A004.z, and 4A005.z); 4D090 (for “software” for commodities controlled by 4A090); 4E001
(for “technology” for commodities controlled by 4A003.z, 4A004.z, 4A005.z, 4A090 or
“software” specified by 4D001 (for 4A003.z, 4A004.z, and 4A005.z), 4D090 (for “software” for
commodities controlled by 4A090)); 5A002.z; 5A004.z; 5A992.z; 5D002.z; 5D992.z; 5E002 (for
“technology” for commodities controlled by 5A002.z or 5A004.z or “software” specified by
5D002 (for 5A002.z or 5A004.z commodities)); or 5E992 (for “technology” for commodities
controlled by 5A992.z or “software” controlled by 5D992.z) without a license if you have
“knowledge” at the time of the export, reexport, or transfer (in-country) that the item is destined

to a data center to or within any destination worldwide that is providing or will provide access to
more than 12,000,000 “aggregate TPP” either at one data center or through ‘linked data centers’
to or for companies headquartered in, or whose ultimate parent company is headquartered in,
Macau or a destination specified in Country Group D:5 in supplement no. 1 to part 740 of the
EAR.
Note 1 to paragraph (a)(1): The prohibitions pursuant to paragraph (a)(1) apply
regardless of whether the person in possession of the EAR item was a party to the transaction to
the original export, reexport, or transfer (in-country) (see § 748.5).
Note 2 to paragraph (a)(1): The prohibitions pursuant to paragraph (a)(1) apply
regardless of whether a U.S.-origin item specified under paragraph (a) of this section has been
incorporated or commingled into or with a foreign-made item. Reexporters and transferors may
not rely on the de minimis provisions for incorporating or commingling U.S.-origin items
specified under paragraph (a) into foreign-made items where there is “knowledge” at any point
in the chain from the “development", “production”, or “use” of the foreign-made item that
incorporates or commingles a U.S.-origin item will be used in a prohibited end-use under
paragraph (a)(1) of this section.
Note 3 to paragraph (a)(1): To satisfy the requirement that you do not have “knowledge”
for purposes of this paragraph, you will be expected to obtain and be able to provide sufficient
information from the foreign data center regarding that data center’s “know your customer” due
diligence checks. Such diligence checks will include diligence on whether any data center
customers are subject to direct or indirect ownership or control by persons located in,
headquartered in, or whose ultimate parent is headquartered in, Macau or a destination
specified in Country Group D:5. A foreign data center declining or being unable to provide
information sufficient to verify compliance with this end use control shall be considered a red
flag that presumptively provides you with “knowledge” unless you are able to resolve that red
flag before proceeding with the transaction.

(2) Additional prohibition on persons informed by BIS. BIS may inform persons, either
individually by specific notice or through amendment to the EAR, that a license is required for
the export, reexport, or transfer (in-country) of specified items to certain persons or destinations,
because there is an unacceptable risk of use in, or diversion to, the activities specified in
paragraph (a)(1) of this section. Specific notice is to be given only by, or at the direction of the
Secretary of Commerce or the Under Secretary of Commerce for Industry and Security. When
such notice is provided orally, it will be followed by a written notice within two working days
signed by the Secretary of Commerce or the Under Secretary of Commerce for Industry and
Security. However, the absence of any such notification does not excuse persons from
compliance with the license requirements of paragraphs (a)(1) of this section. The Secretary of
State or the Assistant to the President for National Security Affairs may notify the Secretary of
Commerce that a certain destination is at high risk of use in, or diversion to, the activities
specified in paragraph (a)(1) of this section. Within 10 days of receipt of such notice, the
Secretary of Commerce shall, if he deems it appropriate, inform persons, either individually by
specific notice or through amendment to the EAR, that a license is required for the export,
reexport, or transfer (in-country) of specific items to that destination.
(b) Exceptions. (1) No license exceptions may overcome the prohibition described in paragraph
(a) of this section, except as noted by BIS when a destination is designated under paragraphs (3)
of this section.
(2) The prohibitions under this section do not apply when the computing power access is only
being provided for a ‘commercial recommender system’ and you submit the following
information to https://www.bis.gov/ai/exclusionnotesubmission, which will be shared with the
End User Review Committee.
(i) The name of the company headquartered in, or whose ultimate parent company is
headquartered in, Macau or a destination specified in Country Group D:5 in supplement no. 1 to
part 740 of the EAR

(ii) The sum of the total processing performance (TPP, as defined in the Technical Notes to
ECCN 3A090) of all of the ICs or commodities specified in paragraph (a)(1) provided to or for
the company specified in (b)(2)(i)
(iii) The due diligence performed to ensure the computing power access is exclusively being
provided for a ‘commercial recommender system.’ (3) Any data center providing significant
volume of compute power to companies headquartered, or with an ultimate parent headquartered,
in Macau or Country Group D:5 prior to the publication date of this rule that wishes to continue
providing these services must obtain a license with 90 days of the effective date of this IFR or
face future export restrictions.
(c) License review policy. Applications for licenses required by this section will be reviewed on
a case-by-case basis.
(d) Definitions. For purposes of this section, the following definitions are applicable:
(1) Commercial recommender system. A commercial recommender system means a Super
Intelligence (SI) tool exclusively designed and exclusively used to rank, filter, or suggest
commercial products, services, or content to users based on user behavior, transaction history, or
item attributes. This term does not include any SI system designed or used to generate novel text,
image, audio, video, software, or other content in response to user inputs, or any system that
incorporates such model, regardless of whether the system also performs recommendation
functions.
(2) Linked data center. For purposes of this section, a ‘linked data center’ means a data center
that uses networking infrastructure that links two or more separate data centers together, through
digitally-linked or physically-linked infrastructure, that allows physical and virtual facilities to
share resources, balance workloads, and replicate data as a unified whole. ‘Linked data center’
includes digitally-linked infrastructure, not just physically-linked infrastructure.
(e) Notification and authorization requirement for subsequent changes in end-use. For any
export, reexport, or transfer made on or after [INSERT DATE OF PUBLICATION IN THE

FEDERAL REGISTER] without authorization, i.e., because the exporter, reexporter, or
transferor had no “knowledge” that the item is for a prohibited end-use under this section and no
other EAR license requirement applies, the exporter, reexporter, or transferor must inform the
recipient that a BIS authorization is required if the item or items will be used at a data center to
provide access to more than 12,000,000 “aggregate TPP” either at one data center or through
‘linked data centers’ to or for companies headquartered in, or whose ultimate parent company is
headquartered in, Macau or a destination specified in Country Group D:5 in supplement no. 1 to
part 740 of the EAR. The notification from the exporter, reexporter, or transferor must also
specify that the transferor, e.g., the data center operator, must obtain authorization for this
change in end-use. The notification from the exporter, reexporter, and transferor must also
specify that the transferor must follow the know-your-customer guidance in supplement no. 3
Part 732 of the EAR.
PART 748
"""


class BisRemoteRuleTests(unittest.TestCase):
    def test_public_inspection_is_not_effective_even_after_scheduled_date(self):
        for now in (NOW, NOW + dt.timedelta(days=3)):
            item = bis.make_item(META, BODY, now, inspection=True)
            self.assertEqual(item["bis_gpu_remote_stage"], "official-public-inspection-2026-23529")
            self.assertIsNone(item["bis_rule_effective_date"])

    def test_published_metadata_in_future_is_rejected(self):
        meta = {**META, "html_url": "https://www.federalregister.gov/documents/2026/11/19/2026-23529/remote-access"}
        # Korea is already on Nov 19; the U.S. legal date is still Nov 18.
        now = dt.datetime(2026, 11, 19, 9, 0, tzinfo=ZoneInfo("Asia/Seoul"))
        self.assertIsNone(bis.make_item(meta, BODY, now, inspection=False))

    def test_effectiveness_requires_resolved_dates_and_actual_publication(self):
        meta = {**META, "html_url": "https://www.federalregister.gov/documents/2026/11/19/2026-23529/remote-access"}
        now = NOW + dt.timedelta(days=3)
        pending = bis.make_item(meta, BODY, now, inspection=False)
        self.assertEqual(pending["bis_gpu_remote_stage"], "official-final-2026-23529")
        active = bis.make_item(meta, BODY.replace("[INSERT DATE OF PUBLICATION IN THE FEDERAL REGISTER]", "November 19, 2026"), now, inspection=False)
        self.assertEqual(active["bis_gpu_remote_stage"], "official-effective-2026-23529")
        self.assertEqual(active["bis_rule_effective_date"], "2026-11-19")

    def test_body_and_metadata_must_both_identify_the_same_rule(self):
        self.assertIsNone(bis.make_item({**META, "document_number": "2026-18535"}, BODY, NOW, inspection=True))
        self.assertIsNone(bis.make_item(META, BODY.replace("0694-AK50", "0694-OTHER"), NOW, inspection=True))
        self.assertIsNone(bis.make_item({**META, "html_url": "https://www.federalregister.gov.attacker.test/public-inspection/2026-23529"}, BODY, NOW, inspection=True))

    def test_condition_change_does_not_reuse_old_exact_numbers(self):
        item = bis.make_item(META, BODY.replace("12,000,000", "13,000,000"), NOW, inspection=True)
        self.assertFalse(item["bis_rule_conditions_verified"])
        self.assertNotIn("12,000,000", " ".join(item["bis_rule_profile"]["actual_bullets"]))

    def test_current_metadata_404_falls_back_to_full_inspection_text(self):
        def fetch(url, timeout=8):
            if url == bis.PUBLISHED_API:
                raise OSError("404")
            return json.dumps(META) if url == bis.INSPECTION_API else BODY
        items = bis.collect_current_bis_items(NOW, fetch)
        self.assertEqual(len(items), 1)
        self.assertEqual(bis.get_source_failures(), [])

    def test_scheduled_publication_0900_boundary_preserves_failure_and_inspection_status(self):
        def fetch(url, timeout=8):
            if url == bis.PUBLISHED_API:
                raise TimeoutError("published API unavailable")
            return json.dumps(META) if url == bis.INSPECTION_API else BODY
        for minute, expected_failures in ((8 * 60 + 59, 0), (9 * 60, 1)):
            now = dt.datetime(2026, 11, 19, minute // 60, minute % 60, tzinfo=bis.EASTERN)
            items = bis.collect_current_bis_items(now, fetch)
            self.assertEqual(len(bis.get_source_failures()), expected_failures)
            self.assertEqual(items[0]["bis_gpu_remote_stage"], "official-public-inspection-2026-23529")
            self.assertIsNone(items[0]["bis_rule_effective_date"])
            if expected_failures:
                self.assertEqual(bis.get_source_failures()[0]["url"], bis.PUBLISHED_API)
                self.assertIn("확인 보류", items[0]["bis_rule_profile"]["stage"])

    def test_changed_operative_threshold_is_detected_even_when_old_number_remains(self):
        changed = BODY.replace("more than 12,000,000", "more than 13,000,000", 1)
        self.assertIn("12,000,000", changed)
        original = bis.make_item(META, BODY, NOW, inspection=True)
        revised = bis.make_item(META, changed, NOW, inspection=True)
        repeated = bis.make_item(META, changed, NOW + dt.timedelta(minutes=15), inspection=True)
        self.assertFalse(revised["bis_rule_conditions_verified"])
        self.assertNotIn("12,000,000", " ".join(revised["bis_rule_profile"]["actual_bullets"]))
        self.assertNotIn("13,000,000", " ".join(revised["bis_rule_profile"]["actual_bullets"]))
        rule = next(r for r in host.STORY_RULES if r.key == host.BIS_GPU_REMOTE_KEY)
        old_key = host.story_event_fingerprint(rule, [original])
        new_key = host.story_event_fingerprint(rule, [revised])
        self.assertNotEqual(old_key, new_key)
        self.assertEqual(new_key, host.story_event_fingerprint(rule, [repeated]))
        self.assertEqual(host.unseen_items_for_rule(rule, [repeated], {new_key: {}}), [])

    def test_appended_conflicting_threshold_is_not_hidden_by_old_word_matches(self):
        changed = BODY + "\nOperative correction: the previous 12,000,000 threshold is replaced by 13,000,000 aggregate TPP."
        item = bis.make_item(META, changed, NOW, inspection=True)
        self.assertFalse(item["bis_rule_conditions_verified"])
        self.assertIn("revision-", item["bis_gpu_remote_stage"])

    def test_whitespace_and_publication_date_resolution_do_not_change_material_revision(self):
        whitespace = BODY.replace(" ", " \n\t").replace("\n", "\n\n")
        item = bis.make_item(META, whitespace, NOW, inspection=True)
        self.assertTrue(item["bis_rule_conditions_verified"])
        self.assertEqual(item["bis_gpu_remote_stage"], "official-public-inspection-2026-23529")
        resolved = re.sub(r"\[INSERT DATE OF PUBLICATION IN (?:THE )?FEDERAL REGISTER\]",
                          "November 19, 2026", bis.plain(BODY))
        meta = {**META, "html_url": "https://www.federalregister.gov/documents/2026/11/19/2026-23529/remote-access"}
        published = bis.make_item(meta, resolved, NOW + dt.timedelta(days=3), inspection=False)
        self.assertTrue(published["bis_rule_conditions_verified"])
        self.assertEqual(published["bis_gpu_remote_stage"], "official-effective-2026-23529")
        self.assertEqual(published["bis_rule_material_signature"], item["bis_rule_material_signature"])

    def test_changed_conditions_leave_source_health_evidence(self):
        changed = BODY.replace("more than 12,000,000", "more than 13,000,000", 1)
        def fetch(url, timeout=8):
            if url == bis.PUBLISHED_API:
                raise OSError("404")
            return json.dumps(META) if url == bis.INSPECTION_API else changed
        items = bis.collect_current_bis_items(NOW, fetch)
        self.assertFalse(items[0]["bis_rule_conditions_verified"])
        self.assertEqual(len(bis.get_source_failures()), 1)
        self.assertIn("material conditions", bis.get_source_failures()[0]["source"])

    def test_outage_has_no_candidate_and_retains_failure_evidence(self):
        def fetch(*args, **kwargs):
            raise TimeoutError("timeout")
        self.assertEqual(bis.collect_current_bis_items(NOW, fetch), [])
        self.assertTrue(bis.get_source_failures())

    def test_current_render_preserves_five_countries_threshold_and_conditions(self):
        item = bis.make_item(META, BODY, NOW, inspection=True)
        rule = next(r for r in host.STORY_RULES if r.key == host.BIS_GPU_REMOTE_KEY)
        report = host.render_alert(rule, [item], NOW)
        for value in ("5개국", "12,000,000", "90일", "추천시스템", "보고 조건", "정식 철회", "관보 미게재"):
            self.assertIn(value, report)
        self.assertNotIn("노르웨이", report)
        self.assertNotIn("남아공", report)
        self.assertLess(len(report), 4096)
        self.assertEqual(host.alert_confirmation_status(rule, [item])[0], "공식 공개열람")

    def test_mirror_dedupes_but_later_effective_stage_does_not(self):
        item = bis.make_item(META, BODY, NOW, inspection=True)
        rule = next(r for r in host.STORY_RULES if r.key == host.BIS_GPU_REMOTE_KEY)
        duplicate = {**item, "source": "Reuters", "link": "https://example.com/reprint"}
        later = {**item, "bis_gpu_remote_stage": "official-effective-2026-23529"}
        first = host.story_event_fingerprint(rule, [item])
        self.assertEqual(first, host.story_event_fingerprint(rule, [duplicate]))
        self.assertNotEqual(first, host.story_event_fingerprint(rule, [later]))
        self.assertEqual(host.unseen_items_for_rule(rule, [item], {first: {}}), [])

    def test_new_official_title_is_not_filtered_out_by_old_ai_vocabulary(self):
        self.assertTrue(host.bis_gpu_remote_official_candidate(META["title"]))
        self.assertFalse(host.bis_gpu_remote_official_candidate("Commerce amends import tariffs"))


if __name__ == "__main__":
    unittest.main()
