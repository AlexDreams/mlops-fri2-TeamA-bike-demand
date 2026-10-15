\# Lab 3 – Dependency lock verification



\*\*Student:\*\* Alexandre Garreau  

\*\*Branch:\*\* `lab3-alexandre-lock`  

\*\*Environment:\*\* Windows PowerShell, Python 3.12, uv 0.12.24



\## Objective



I checked that the project dependencies are locked and that a missing lockfile causes a clear failure.



\## Successful checks



I ran the following commands from the project directory:



`uv lock --check`



Observed result:



`Resolved 98 packages in 3ms`



I then ran:



`uv sync --locked`



Observed result:



`Resolved 98 packages in 2ms`  

`Checked 97 packages in 643ms`



These commands completed successfully without changing the project's lockfile.



\## Missing lockfile test



I created a temporary directory outside the Git repository and copied only `pyproject.toml` into it.



I ran:



`uv lock --check`



The command failed with the following error:



`Unable to find lockfile at uv.lock, but --check was provided.`



This is the expected failure because the temporary directory does not contain `uv.lock`.



\## Conclusion



The existing dependency lock is valid, and the locked installation check succeeds on my Windows environment.



The negative test demonstrates that `uv lock --check` does not silently create a missing lockfile.



I did not modify `uv.lock`, the source code or the original dataset.



\## Assistance and references



I used the official MLOps course instructions and the Astral uv documentation to understand dependency locking and verification.



I also received assistance in preparing the PowerShell commands and organizing the verification steps.



I executed the commands myself, checked the results, and confirmed that the missing-lockfile test failed as expected.



\*\*References:\*\*

\- https://github.com/minhtc-uca/mlops-course

\- https://docs.astral.sh/uv/concepts/projects/sync/

\- https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.management/push-location



