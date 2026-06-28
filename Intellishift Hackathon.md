What the system must do beyond normalizing DB

- detects location and routing the nearest warehouse to the order location 
- If the delays increase in a specific mode in a specific state go into a multiple checks of why this is happening, is it related to a non availabily of a ware house near this address using the postal codes or a deffecincy in staff work,  or a product issue related matter, all of this should be checked , how to do this for our hackathon is adding leading mock entities in the database and actually making an ai train or make an algorithm that gives back an answer of what is the exact cause via a sequence of if condition above some thresholds on some existing or mocked database entiteies/attributes
- Give any lead-endpoints for forming marketing campaigns or actual algorithms to market for a specific product or an ai agent that provides to the CEO reccomendations on products that would fit our top customer needs 
- matching names algorithms or location precsision ex: 
**Data governance**

Instead of accepting "Apple Valley"

your system asks

> Which Apple Valley?
> 
> - Minnesota
> - California

No ambiguity enters the database.

---

**Master Data Management**

If

```
Sean MillerSean A. MillerS. Miller
```

appear,

the system recognizes they're likely the same customer and suggests merging them.


- Data lineage 
when the ceo asks why did revenue drop X , your system trace back recent transactions and make a story out of it , it doesnt need ai btw 

- adding virtual IOT data to the db and making something with it in the operational decsicion reccomendation is a nice touch and needed but what exactly i dont know 

- AI 1:is a necessity but we will build an AI agent using opensource locally runned on my pc using any free langauge model to have some data from a query/anomaly from our db directly and give out a suggestion or an alert or a reccomendation, and to reccomend anything in selling , you need something time aware and frequently retrained on new data so it gets updated 
- AI 2 : use symbolic ai using semantic meanings to reccomend products to customers with an overlapping purchases algorithm that tracks this mess
- the symbolic ai will be a more grounded option so we dont get chained and put by the judges in the zone of the AI slop 
- score =
distance
+
stock availability
+
delivery estimate
+
warehouse load


- Build a rule engine.

Think of it like

```
Rule 1IFdelay > thresholdANDwarehouse stock lowTHENlikely inventory shortage
```

```
Rule 2delay+staff overtime↓staff bottleneck
```

Much cleaner.

- No IOT needed it will look very out of context instead just simulate getting on the ground data like 
  Create believable operational events.

Example

Warehouse table

```
warehouse_idcapacitycurrent_loadstaff_on_shiftloading_queue
```

Carrier table

```
carrieractive trucksaverage delay
```

Inventory table

```
productwarehousestockreservedincoming
```

Those are enough.

No fake IoT needed.

