# Photobooth modules

The code is split into two standalone projects:

- [Raspberry_Pi](./Raspberry_Pi/README.md): copy this folder to the Raspberry Pi.
- [Server_Module](./Server_Module/README.md): run this folder on the PC/laptop.

Each project contains its own configuration, dependencies, and `shared/`
protocol package, so it can be installed and run independently. Keep the two
copies of `shared/` in sync when changing message schemas or MQTT topics.

The original project documents remain at this folder's root.
