# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
This file contains various sanity checks for Glean.
"""

import os

from schema import And, Optional, Schema


def check_glean_metric_structure(data):
    schema = Schema(
        {
            str: {
                Optional(And(str, lambda x: len(x) == 40)): [
                    And(str, lambda x: os.path.exists(x))
                ]
            }
        }
    )

    schema.validate(data)


DUPLICATE_METRICS_EMAIL_TEMPLATE = """
Glean has detected duplicated metric identifiers coming from the product '{repo.name}'.

{duplicates}

What to do about this:

1. File a bug to track your investigation. You can just copy this email into the bug Description to get you started.
2. Reply-All to this email to let the list know that you are investigating. Include the bug number so we can help out.
3. Rename the most recently added metric to be more specific. See [1]
4. Make sure a Glean team member reviews any patches. Care needs to be taken that the resolution of this problem is schema-compatible.

If you have any problems, please ask for help on the #glean Slack channel. We'll give you a hand.

What this is:

We have a system called probe-scraper [2] that scrapes the metric information from all Mozilla products using the Glean SDK. All the scraped data is available on the probeinfo service [3]. The scraped definition is used to build things such as the probe-dictionary [4] and other data tools. It detected that one metric that was recently added has an identifier collision with some metric that already existed in the application namespace. So it sent this email out, encouraging you to fix the problem.

What happens if you don't fix this:

The metrics will compete to send their data in pings, making the data unreliable at best.

You can do this!

Your Friendly, Neighborhood Glean Team

[1] - https://mozilla.github.io/glean/book/user/adding-new-metrics.html#naming-things
[2] - https://github.com/mozilla/probe-scraper
[3] - https://probeinfo.telemetry.mozilla.org/
[4] - https://telemetry.mozilla.org/probe-dictionary/
""" # noqa


def check_for_duplicate_metrics(repositories, metrics_by_repo, emails):
    """
    Checks for duplicate metric names across all libraries used by a particular application.
    It only checks for metrics that exist in the latest (master) commit in each repo, so that
    it's possible to remove (or disable) the metric in the latest commit and not have this
    check repeatedly fail.
    If duplicates are found, e-mails are queued and this returns True.
    """
    found_duplicates = False

    repo_by_library_name = {}
    repo_by_name = {}
    for repo in repositories:
        for library_name in repo.library_names or []:
            repo_by_library_name[library_name] = repo.name
        repo_by_name[repo.name] = repo

    for repo in repositories:
        dependencies = [repo.name] + [
            repo_by_library_name[library_name] for library_name in repo.dependencies
        ]

        metric_sources = {}
        for dependency in dependencies:
            for metric_name in metrics_by_repo[dependency].keys():
                metric_sources.setdefault(metric_name, []).append(dependency)

        duplicate_sources = dict(
            (k, v) for (k, v) in metric_sources.items() if len(v) > 1
        )

        if not len(duplicate_sources):
            continue

        found_duplicates = True

        addresses = set()
        duplicates = []
        for name, sources in duplicate_sources.items():
            duplicates.append(
                "- {!r} defined more than once in {}".format(
                    name, ", ".join(sorted(sources))
                )
            )

            for source in sources:
                # Send to the repository contacts
                addresses.update(repo_by_name[source].notification_emails)

                # Also send to the metric's contacts
                for history_entry in metrics_by_repo[source][name]["history"]:
                    addresses.update(history_entry["notification_emails"])

        duplicates = "\n".join(duplicates)

        emails[f"duplicate_metrics_{repo.name}"] = {
            "emails": [
                {
                    "subject": "Glean: Duplicate metric identifiers detected",
                    "message": DUPLICATE_METRICS_EMAIL_TEMPLATE.format(
                        duplicates=duplicates, repo=repo
                    ),
                }
            ],
            "addresses": list(addresses),
        }

    return found_duplicates
