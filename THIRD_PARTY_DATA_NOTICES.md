# Third-Party Data Notices

## Open Food Facts

Source:

Open Food Facts

https://world.openfoodfacts.org/data

Database licence:

Open Data Commons Open Database License 1.0

https://opendatacommons.org/licenses/odbl/1-0/

Individual contents licence:

Open Data Commons Database Contents License 1.0

https://opendatacommons.org/licenses/dbcl/1-0/

Attribution notice:

Contains information from Open Food Facts, which is made available
under the Open Database License (ODbL).

MostoFit modifies the source database by:

- filtering products by country;
- selecting app-facing fields;
- selecting nutrition values per 100 g;
- converting kilojoules to kilocalories when necessary;
- normalizing selected serving units;
- removing records without usable nutrition information;
- deduplicating products;
- sorting products using popularity information where available;
- limiting large packs to a configured size budget;
- splitting large packs into app-facing files;
- converting the source export to JSON.

The generated packs do not contain Open Food Facts product images.

Open Food Facts data is collaboratively submitted and may be
incomplete or inaccurate. MostoFit does not represent the generated
packs as official nutritional or medical advice.
