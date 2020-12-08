# Factory Tools
This folder provides tools that are useful for managing factory repo and factory
flow.

## `download_patch.py`
When we are releasing factory toolkit or bundle, sometimes, especially in early
build phase, we need to cherry-pick some workarounds that haven't / cannot be
merged into ToT.  Manually cherry picking these workarounds is a tedious
process, this tool helps you automate the process.

This tool uses `topic` or `hashtag` to filter changes on Gerrit.  Each change
can only have one topic but can have multiple hashtags.

### Assign Topic to Changes
There are three ways you can set topic of a change:
* Go to `https://crosreview.com/<CL>`, change the topic field manually.
* `repo upload -t`  (use branch name as topic)
* `gerrit topic abc 439944`


### Add Hashtags to Changes
There are three ways you can set hashtags on a change:
* Go to `https://crosreview.com/<CL>`, change the hashtag field manually.
* `repo upload -o hashtag=<hashtag>`
* Command line: `gerrit sethashtags <CL> tag_to_add ~tag_to_remove ...`

### Examples and Explanations
```bash
git stash  # you cannot cherry-pick CLs if there are unstaged changes
# First of all, download unmerged changes that fix download_patch.py.
py/tools/download_patch.py --hashtag fix-download-patch
```
Above command downloads changes with hashtag `fix-download-patch` on Gerrit in
*factory repository*.  The following things will happen:

1. Stash all unstaged local changes.
2. Check out `cros/main` (the remote main branch) of factory repo.
3. Cherry-pick changes with hashtag `fix-download-patch` from Gerrit.  The
   program tries its best to resolve dependencies between each changes.
4. Print a summary line showing CLs that successfully downloaded and CLs that
   failed to download.

```bash
py/tools/download_patch.py --topic spring-factory --board spring \
    --branch factory-spring-4262.B
```
Above command will perform the following steps:

1. In *factory repo*
    1. Check out `cros/factory-spring-4262.B`
    2. Cherry-pick changes with topic `spring-factory` on branch
       `factory-spring-4262.B`.
    3. Print a summary line
2. In *spring overlay*
    1. Check out `cros/factory-spring-4262.B`
    2. Cherry-pick changes with topic `spring-factory` on branch
       `factory-spring-4262.B`.
    3. Print a summary line

If both `topic` and `hashtag` are provided, this will limit the program to
download changes has given `topic` *and* given `hashtag`.  Currently, we don't
support multiple hashtags (disjunction nor conjunction).
