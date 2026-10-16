# Lumen LR7 Series Product Specification

This document specifies the Lumen LR7 series of autonomous mobile robots for warehouse intralogistics. It covers the two production models, the LR7-X2 and the LR7-S1, their mechanical dimensions, battery system, sensors, safety functions and software requirements. It is written for integrators, safety officers and facility planners. Commercial terms are handled separately by the sales team and are not part of this specification.

## Overview

The LR7 series carries totes, cartons and small pallets between storage racks, packing stations and loading docks. The robots navigate without floor markings by combining a 360 degree lidar scanner, wheel odometry and a map of the facility that is built during commissioning. A fleet of up to 400 robots can be coordinated by one fleet service instance, and the robots are controlled through the Lumen Fleet API.

Two models share the same software and the same docking infrastructure. The LR7-X2 is the standard model for loads up to 40 kilograms and is sold under SKU 70-2210. The LR7-S1 is a compact model for narrow aisles and is sold under SKU 70-2105. Both are delivered with a safety scanner, a battery pack and a quick start kit.

## Dimensions and weight

The LR7-X2 measures 1,120 mm in length, 740 mm in width and 420 mm in height with the standard deck. Its unladen weight is 86 kg, including the battery pack. The deck surface is 1,000 mm long and 700 mm wide and sits 380 mm above the floor.

The LR7-S1 is smaller. It measures 860 mm in length, 560 mm in width and 360 mm in height, and its unladen weight is 52 kg. The deck of the S1 is 760 mm long and 520 mm wide. The S1 fits through aisles as narrow as 900 mm, while the X2 requires at least 1,300 mm for turning.

The rated payload is 40 kg for the LR7-X2 and 12 kg for the LR7-S1. The payload is the maximum mass on the deck, including any accessory that is mounted on it. The load should be centred within 100 mm of the middle of the deck to preserve the rated stopping distance.

## Drive and motion

Both models use a differential drive with two hub motors and two passive casters. The LR7-X2 has two 400 W hub motors and wheels of 200 mm diameter made of polyurethane. The maximum speed of the LR7-X2 is 2.2 metres per second when unladen and 1.5 metres per second at full payload. The robot accelerates at up to 0.8 metres per second squared.

The X2 can climb ramps with a gradient of up to 5 percent and cross floor gaps of up to 15 mm. Larger gaps and steps require a bridging plate. The turning radius is zero, because the robot can rotate on the spot. Positioning accuracy at a workstation is plus or minus 10 mm without a docking marker and plus or minus 3 mm with one.

The motion controller limits speed automatically when the robot carries a load higher than 30 kg, when it travels in a zone marked as pedestrian area, and when the floor friction estimate falls below the configured threshold. Speed zones are set in the facility map by the commissioning engineer.

## Battery and charging

The LR7-X2 is powered by the battery pack LB-48-30. It is a lithium iron phosphate pack with a nominal voltage of 48 V and a capacity of 30 Ah, which corresponds to an energy content of 1,440 Wh. The pack weighs 11.4 kg and can be exchanged in under two minutes without tools. A spare pack is available as SKU 80-4830.

The LR7-S1 uses the smaller LB-36-20 pack with 36 V, 20 Ah and 720 Wh. This gives the S1 a typical runtime of 7 hours, compared with 9.5 hours for the X2 in a typical shift with an average load of 20 kg and a mix of driving and waiting.

Charging is done with the dock LD-300. At the dock, the LR7-X2 charges from 0 to 80 percent in 52 minutes, and a full charge to 100 percent takes 85 minutes. The robot connects to the dock automatically through contacts on its front plate. Opportunity charging for short periods during idle time is supported and does not harm the pack.

The battery management system protects the pack against deep discharge. By default, the robot drives to the nearest free dock when the charge falls to 20 percent. The cells are rated for 1,500 full charge cycles before the capacity falls to 80 percent of the original value. The pack should be stored at a charge of about 50 percent if it is not used for more than a month.

Battery packs are classified as dangerous goods when shipped. Follow the transport instructions on the label and use only approved packaging.

## Sensors and perception

The primary sensor is the lidar scanner LS-360, mounted at a height of 190 mm on the front of the robot. It has a range of 25 metres and an angular resolution of 0.25 degrees and delivers 20 scans per second. A second, safety rated scanner covers the rear and sides of the robot.

In addition to the lidar, the robots are equipped with four depth cameras that detect obstacles above and below the lidar plane, such as pallet forks and overhanging cartons. An inertial measurement unit tracks tilt and vibration. Wheel encoders provide odometry with a resolution of 4,096 counts per revolution.

Localisation relies on matching lidar scans with the facility map. If the robot loses its position, it stops and requests help from the fleet service, and it can usually relocalise by itself after driving a few metres. In large open areas without features, reflective markers can be added to the walls.

The onboard computer has eight CPU cores and 32 GB of memory, and it runs navigation, perception and safety supervision in separate processes. Map data and logs are stored on a 256 GB solid state drive.

## Safety

The LR7 series is designed to meet the requirements of ISO 3691-4 for driverless industrial trucks. The safety functions are implemented on a separate controller that does not depend on the main computer. If the protective field of the safety scanner is violated, the robot performs a protective stop.

At full speed the LR7-X2 comes to a complete stop within 0.4 metres after a protective stop is triggered. The protective field adapts to the speed of the robot, and warning fields give pedestrians visible and audible notice before a stop becomes necessary. Each robot has four emergency stop buttons, one at each corner, which cut power to the drive motors.

Status is shown by a light ring around the top of the robot. Green means ready, blue means the robot is driving a mission, amber means that it is waiting or charging, and red means a fault. The light ring flashes when the identify command is received.

The robot emits an audible signal when it reverses, with a volume that is adjustable in the site settings. Integrators are responsible for the site risk assessment, including pedestrian separation and the handling of loads that are higher than the deck.

## Environment

The LR7 series is designed for indoor use on flat, hard floors such as sealed concrete. The operating temperature range is 0 to 40 degrees Celsius, and the relative humidity must be between 10 and 90 percent without condensation. In cold storage environments a special variant is planned but is not part of this specification.

Storage temperature for robots with batteries removed is minus 20 to 50 degrees Celsius. The robots must not be used in explosive atmospheres, and they should be kept away from sources of strong electromagnetic interference such as large induction heaters.

## Connectivity and software

Robots connect to the fleet service through dual band Wi-Fi 6. An optional LTE module, sold as SKU LM-4G, provides a fallback connection when the facility network is not available. Roaming between access points takes less than 150 ms when the access points are configured as described in the network guide.

The LR7-X2 requires firmware version v3.2.0 or later. The LR7-S1 requires v3.3.0 or later. Firmware is updated over the air from the fleet service, and a robot downloads an update while it charges and installs it only when it is idle at the dock. Rolling back to the previous firmware is possible during the first 7 days after an update.

Integrators use the Lumen Fleet API to create missions and to read telemetry. Direct access to the robot over the network is possible only for the commissioning engineer, using the service port on the rear panel.

## Accessories

The following accessories are available for the LR7 series. The lift tray LA-118, sold as SKU 90-1180, raises the load by up to 300 mm and is intended for transfers to shelves and workstations. It adds 14 kg to the weight of the robot, which reduces the usable payload by the same amount when the tray is fitted to the LR7-S1.

The roller conveyor top LA-204 moves cartons on and off the robot at conveyor stations. The tote guide LA-310 keeps standard 600 by 400 mm totes in position on the deck during acceleration. Other accessories include a warning beacon, reflective navigation markers and a mounting kit for custom load carriers.

All accessories are detected automatically through a connector on the deck, and the robot adjusts its speed limits and stopping distances to the accessory that is fitted.

## Maintenance

The robots are designed for low maintenance. Every 6 months or 2,000 operating hours, whichever comes first, the wheels, casters and dock contacts should be inspected, and the lidar window should be cleaned with a lint free cloth. Wheels are replaced when the tread has worn down to 6 mm.

Firmware logs are uploaded automatically and can be analysed by Lumen support. A diagnostic report can be generated from the customer console, and it lists battery health, motor currents and the number of protective stops in the last 30 days.

Only trained personnel should open the robot housing. Before any work on the drive or on the battery compartment, switch the robot off with the main switch and wait one minute for the capacitors to discharge.
