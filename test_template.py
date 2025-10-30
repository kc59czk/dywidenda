import os
import importlib.util
import pathlib

# Load app.py as a module regardless of package layout
spec = importlib.util.spec_from_file_location(
    "local_app", str(pathlib.Path(__file__).parent / "app.py")
)
app_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_mod)

app = app_mod.create_app()
print('Flask template_folder:', app.template_folder)
print('Absolute path:', os.path.abspath(app.template_folder))
print('\nFiles in template folder:')
for root, dirs, files in os.walk(app.template_folder):
    for f in files:
        print(' -', os.path.join(root, f))

print('\nJinja template list sample:')
try:
    templates = list(app.jinja_env.list_templates())
    print('Total templates Jinja knows about:', len(templates))
    for t in templates[:50]:
        print(' *', t)
except Exception as e:
    print('Could not list templates from Jinja:', e)
