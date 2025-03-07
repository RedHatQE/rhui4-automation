About
---------------
Setup of the RHUI 4 Test Framework

Requirements
---------------
* Have Python 3.
* Have the latest released RHUI 4 ISO. If you use an older ISO, you will get failures from the test
cases that cover bug fixes or features from newer releases. Alternatively, you can supply Red Hat
CCSP credentials so that RHUI packages can be installed from the Red Hat CDN.

Note: if you supply the credentials to have the systems registered, remember to unregister
the systems before you delete the stack to save available entitlements.
You can do so by running `rhuiunregistersm` on the test machine.
You can also run this anytime while using the stack.
Should you need to register the systems again while the stack is active, run `rhuiregistersm`.

Environment
---------------
Run the [stack creation script](../scripts/README.md) to launch VMs and get an inventory file
with information about the VMs; be sure to include:
* one or more client machines
* a test machine

Deployment
--------------
Run the [deployment script](../scripts/deploy.py) to deploy RHUI on the VMs.

You need a ZIP file with the following files in the root of the archive:

* `rhcert.pem` — This must be a valid Red Hat content certificate allowing access to the repositories used in `rhui4_tests/tested_repos.yaml`.
* `rhcert.mapping` — Optional; a copy of the repo cache for rhcert.pem, taken from an existing RHUA. Using this file will speed up adding repos significantly.
* `rhcert_empty.pem` — This must be a Red Hat content certificate containing no entitlement.
* `rhcert_expired.pem` — This must be an expired Red Hat content certificate.
* `rhcert_incompatible.pem` — This must be a Red Hat content certificate containing one or more entitlements that are not compatible with RHUI (containing a non-RHUI repository path) and no compatible entitlement at all.
* `rhcert_partially_invalid.pem` — This must be a Red Hat content certificate containing one or more entitlements that are not compatible with RHUI (containing a non-RHUI repository path) but also at least one compatible entitlement.
* `entcert_longlife.crt` — This must be an entitlement certificate that expires far in the future, in 25 years or later.
* `rhui-rpm-upload-test-1-1.noarch.rpm` — This package will be uploaded to a custom repository.
* `rhui-rpm-upload-trial-1-1.noarch.rpm` — This package will also be uploaded to a custom repository. It must be signed with the RHUI QE GPG key.
* `rhui-rpm-upload-tryout-1-1.noarch.rpm` — This package will also be uploaded to a custom repository. It must be signed with a key different from RHUI QE.
* `test_gpg_key` — This is the RHUI QE public GPG key (0x9F6E93A2).
* `ANYTHING.tar` — These must be tarballs containing some packages and their `updateinfo.xml.gz` files. The contents will be used for updateinfo testing. Exact names are to be specified in `rhui4_tests/tested_repos.yaml`. One of them must also contain an uncompressed updateinfo file.
* `legacy_ca.crt` — This must be a CA certificate taken from a different RHUI environment; ie. `/etc/pki/rhui/certs/entitlement-ca.crt` in the case of RHUI 3, or `/etc/pki/rhui/certs/ca.crt` if using a CA cert from RHUI 4. The file will be used in legacy CA testing.
* `SCA/ID.pem, SCA/ID-key.pem` — These must be an entitlement certificate and its key for Simple Content Access. Note that `SCA` is an actual directory name, whereas `ID` is supposed to be the serial number of the certificate in question.
* `custom_certs/FILES`: Several files that will be used to test custom CA certificate handling in rhui-installer and custom certificate handling in CDS registration. The following content is expected:

```
custom_certs/
custom_certs/ca.crt
custom_certs/ca.key
custom_certs/client_entitlement_ca.crt
custom_certs/client_entitlement_ca.key
custom_certs/client_ssl_ca.crt
custom_certs/client_ssl_ca.key
custom_certs/ssl.crt
custom_certs/ssl.key
```

* `comps/[REPO1,REPO2,...]/comps.xml`: Files that will be used to test comps XML handling. The REPO names are specified in `rhui4_tests/tested_repos.yaml`. The second one must also contain a file named `mod-comps.xml`, which is a copy of `comps.xml` with one more package group named `Misc 2`. The `no_comps` comps XML file must not contain any package group.
* `repo_files/FILES`: Several files that will be used to test the ability to add repos specified in a file. Details are in `test_cmdline.py`, but in a nutshell the following content is expected:

```
repo_files/good_repos.yaml
repo_files/bad_ids.yaml
repo_files/bad_name.yaml
repo_files/no_name.yaml
repo_files/no_repo_ids.yaml
repo_files/wrong_repo_id.yaml
```

The main and Atomic certificates must not be expired. Expiration is first checked for the "empty",
"incompatible", and "partially invalid" certificates, and the tests that use them are skipped if
the given certificate has already expired.

If you're working on changes to rhui4-automation that aren't in the default branch and you'd like to
apply them before installing rhui4-automation and running tests, you can supply a patch file
with the changes.

Lastly, in order for several test to be able to run, you need a file with valid Red Hat CCSP
credentials and Quay.io credentials. The file must look like this:

```
[rh]
username=YOUR_RH_USERNAME
password=YOUR_RH_PASSWORD

[quay]
username=YOUR_QUAY_USERNAME
password=YOUR_QUAY_PASSWORD
```

Usage
--------
To install and test RHUI, run:

```
./scripts/deploy.py hosts_ID.cfg --tests X
```

Where _X_ can be one of:

* `all`: to run all RHUI tests
* `client`: to run RHUI client tests
* _name_: to run test\_name\_.py from the [rhui4\_tests](./rhui4\_tests) directory.

Note that it can take a few hours for all the test cases to run.
If you only want to install the test machine, do not use the `--tests` argument.

The test cases will be installed in the `/usr/share/rhui4_tests_lib/rhui4_tests/` directory
and the libraries in the `/usr/lib/pythonVERSION/site-packages/rhui4_tests_lib/` directory
on the TEST machine.
The output of the tests will be stored in a local report file, whose name will be printed.

If you now want to run the tests, or if you want to run them again, you have two options.
Either use _Ansible_ again as follows:

```
./scripts/deploy.py hosts_ID.cfg --tests X --tags run_tests
```

Or log in to the TEST machine, become root, and run:

`rhuitests X`
